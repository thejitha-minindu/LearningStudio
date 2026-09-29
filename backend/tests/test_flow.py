import copy
import io
import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select
from app.contracts import Audit
from app.db import Attempt, Job, Lesson, Passage, Plan, Source, Task, TopicState
from app.extraction import extract
from app.fixtures import FixtureGenerator, FixtureSearch
from app.learning import citations_exist
from app.providers import ProviderError
from app.worker import claim, process, run_once
from conftest import task_payload


def create_process(setup, payload=None):
    client, factory, cfg = setup
    payload = payload or task_payload()
    response = client.post('/tasks', json=payload)
    assert response.status_code == 201, response.text
    response = client.post(f'/tasks/{payload["task_id"]}/process')
    assert response.status_code == 202
    assert response.json()['status'] == 'queued'
    assert run_once(factory, cfg)
    status = client.get(f'/tasks/{payload["task_id"]}').json()
    assert status['status'] == 'ready', status
    return payload['task_id']


def test_no_documents_full_flow_and_citations(setup):
    client, factory, _ = setup
    task_id = create_process(setup)
    state = client.get(f'/tasks/{task_id}').json()
    assert state['research']['queries']
    assert state['research']['live_research'] is False
    assert state['research']['mode'] == 'fixture'
    plan = client.get(f'/tasks/{task_id}/plan').json()
    assert plan['planned_minutes'] <= 60
    assert all(s['estimated_minutes'] <= 20 for s in plan['sessions'])
    lesson = client.get(f'/tasks/{task_id}/lessons').json()[0]
    assert 'answer' not in lesson['questions'][0]
    for section in lesson['sections']:
        for cite in section['citations']:
            passage = client.get(f'/tasks/{task_id}/passages/{cite["passage_id"]}')
            assert passage.status_code == 200
            assert passage.json()['source_id'] == cite['source_id']
    progress = client.get(f'/tasks/{task_id}/progress').json()
    assert all(s['state'] == 'unknown' for s in progress['topic_states'])
    response = client.post(f'/tasks/{task_id}/answers', json={'attempt_id': 'attempt-1', 'lesson_id': lesson['lesson_id'], 'question_id': 'check', 'answer': '-1'})
    assert response.status_code == 200, response.text
    assert response.json()['topic_state']['state'] == 'developing'
    assert response.json()['next_step']['action'] == 'study'
    response = client.post(f'/tasks/{task_id}/answers', json={'attempt_id': 'attempt-2', 'lesson_id': lesson['lesson_id'], 'question_id': 'transfer', 'answer': 'The feature order must match each weight, or the weighted sum changes.'})
    assert response.status_code == 200, response.text
    assert response.json()['result']['method'] == 'fixture_keyword_demo'
    assert response.json()['result']['confidence'] < .7
    assert response.json()['next_step']['action'] == 'generate'
    assert client.post(f'/tasks/{task_id}/next').status_code == 202
    run_once(factory)
    assert len(client.get(f'/tasks/{task_id}/lessons').json()) == 2


def test_exam_supplied_scope_and_supplement(setup):
    client, _, _ = setup
    upload = client.post('/uploads', files={'file': ('syllabus.txt', b'Exam scope: relations and keys, SQL joins, normalization and functional dependencies.', 'text/plain')}).json()
    lecture = client.post('/uploads', files={'file': ('lecture.txt', b'A primary key uniquely identifies each row in a relation. Foreign keys reference related rows.', 'text/plain')}).json()
    payload = task_payload(purpose='exam', resources=[{'kind': 'file', 'value': upload['file_id'], 'role': 'syllabus'}, {'kind': 'file', 'value': lecture['file_id'], 'role': 'lecture'}])
    payload['objective'] = 'Prepare for a database exam on relations, joins and normalization'
    create_process(setup, payload)
    state = client.get('/tasks/task-1').json()
    assert state['research']['queries']
    plan = client.get('/tasks/task-1/plan').json()
    assert plan['purpose'] == 'exam' and plan['scope_status'] == 'supplied'
    sources = client.get('/tasks/task-1/sources').json()
    assert any(s['origin'] == 'supplied' and s['role'] == 'syllabus' for s in sources)
    assert any(s['origin'] == 'fixture' for s in sources)
    lesson = client.get('/tasks/task-1/lessons').json()[0]
    assert any('exam' in s['heading'].lower() for s in lesson['sections'])


@pytest.mark.parametrize('purpose', ['long_term', 'practical', 'exam'])
@pytest.mark.parametrize('has_file', [True, False])
def test_mode_comes_from_purpose_and_exam_scope_uncertain(setup, purpose, has_file):
    client, _, _ = setup
    refs = []
    if has_file:
        upload = client.post('/uploads', files={'file': ('notes.txt', b'A vector is an ordered list of numbers. A weighted sum multiplies inputs and weights.', 'text/plain')}).json()
        refs = [{'kind': 'file', 'value': upload['file_id'], 'role': 'reference'}]
    create_process(setup, task_payload(purpose=purpose, resources=refs))
    plan = client.get('/tasks/task-1/plan').json()
    assert plan['purpose'] == purpose
    assert plan['scope_status'] == ('provisional' if purpose == 'exam' else 'not_applicable')
    if purpose == 'exam':
        assert any('scope is unavailable' in s for s in plan['assumptions'])


@pytest.mark.parametrize('budget', [1, 14, 15, 25, 35, 59, 60])
def test_budget_deferred_and_session_limits(setup, budget):
    client, _, _ = setup
    create_process(setup, task_payload(total=budget))
    plan = client.get('/tasks/task-1/plan').json()
    assert plan['planned_minutes'] <= budget
    assert sum(t['estimated_minutes'] for t in plan['topics']) == plan['planned_minutes']
    assert all(s['estimated_minutes'] <= 20 for s in plan['sessions'])
    if budget < 60:
        assert plan['deferred']


def test_support_inserted_and_time_recalculated(setup):
    client, factory, _ = setup
    create_process(setup)
    lesson = client.get('/tasks/task-1/lessons').json()[0]
    response = client.post('/tasks/task-1/answers', json={'attempt_id': 'wrong', 'lesson_id': lesson['lesson_id'], 'question_id': 'check', 'answer': '3'})
    assert response.json()['topic_state']['state'] == 'needs_support'
    assert response.json()['next_step']['action'] == 'support'
    plan = client.get('/tasks/task-1/plan').json()
    assert plan['topics'][0]['variant'] == 'support'
    assert plan['planned_minutes'] <= plan['remaining_minutes']
    assert plan['deferred']
    client.post('/tasks/task-1/next')
    run_once(factory)
    lessons = client.get('/tasks/task-1/lessons').json()
    assert len(lessons) == 2 and lessons[1]['variant'] == 'support'
    response = client.patch('/tasks/task-1/time', json={'total_minutes': 20, 'session_minutes': 10})
    assert response.status_code == 200
    assert response.json()['planned_minutes'] <= response.json()['remaining_minutes']


def test_idempotent_tasks_jobs_and_attempts(setup):
    client, factory, _ = setup
    payload = task_payload()
    client.post('/tasks', json=payload)
    assert client.post('/tasks', json=payload).json()['reused']
    client.post('/tasks/task-1/process')
    client.post('/tasks/task-1/process')
    run_once(factory)
    assert not run_once(factory)
    changed = {**payload, 'objective': 'Different objective'}
    assert client.post('/tasks', json=changed).status_code == 409
    lesson = client.get('/tasks/task-1/lessons').json()[0]
    answer = {'attempt_id': 'one', 'lesson_id': lesson['lesson_id'], 'question_id': 'check', 'answer': '-1'}
    assert client.post('/tasks/task-1/answers', json=answer).status_code == 200
    assert client.post('/tasks/task-1/answers', json=answer).json()['reused']
    assert client.post('/tasks/task-1/answers', json={**answer, 'answer': '3'}).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1


def test_provider_failure_is_actionable_and_retryable(setup, monkeypatch):
    client, factory, cfg = setup
    class BrokenSearch:
        def search(self, query):
            raise ProviderError('Search unavailable. Check TAVILY_API_KEY and retry.')
    monkeypatch.setattr('app.worker.providers', lambda c: (BrokenSearch(), FixtureGenerator()))
    client.post('/tasks', json=task_payload())
    client.post('/tasks/task-1/process')
    run_once(factory)
    status = client.get('/tasks/task-1').json()
    assert status['status'] == 'failed' and 'TAVILY_API_KEY' in status['error']
    monkeypatch.setattr('app.worker.providers', lambda c: (FixtureSearch(), FixtureGenerator()))
    assert client.post('/tasks/task-1/process').status_code == 202
    run_once(factory)
    assert client.get('/tasks/task-1').json()['status'] == 'ready'


def test_invalid_citations_and_unsupported_generation_rejected(setup, monkeypatch):
    client, factory, _ = setup
    create_process(setup)
    with factory() as db:
        lesson = db.scalar(select(Lesson))
        bad = copy.deepcopy(lesson.data)
        bad['sections'][0]['citations'][0]['passage_id'] = 'invented'
        with pytest.raises(ProviderError, match='citation'):
            citations_exist(db, 'task-1', bad)

        # Test hyphenated IDs auto-heal
        hyphenated = copy.deepcopy(lesson.data)
        orig_s = hyphenated['sections'][0]['citations'][0]['source_id']
        orig_p = hyphenated['sections'][0]['citations'][0]['passage_id']
        if len(orig_s) == 32:
            hyphen_s = f"{orig_s[:8]}-{orig_s[8:12]}-{orig_s[12:16]}-{orig_s[16:20]}-{orig_s[20:]}"
            hyphenated['sections'][0]['citations'][0]['source_id'] = hyphen_s
            citations_exist(db, 'task-1', hyphenated)
            assert hyphenated['sections'][0]['citations'][0]['source_id'] == orig_s

        # Test swapped IDs auto-heal
        swapped = copy.deepcopy(lesson.data)
        swapped['sections'][0]['citations'][0]['source_id'] = orig_p
        swapped['sections'][0]['citations'][0]['passage_id'] = orig_s
        citations_exist(db, 'task-1', swapped)
        assert swapped['sections'][0]['citations'][0]['source_id'] == orig_s
        assert swapped['sections'][0]['citations'][0]['passage_id'] == orig_p

        # Test index reference auto-heal
        indexed = copy.deepcopy(lesson.data)
        indexed['sections'][0]['citations'][0]['passage_id'] = 'passage_1'
        citations_exist(db, 'task-1', indexed)
        assert indexed['sections'][0]['citations'][0]['passage_id'] == orig_p
    class Unsupported(FixtureGenerator):
        def generate(self, schema, instruction, data):
            if schema is Audit:
                return Audit(support='unsupported', explanation='Claims not supported', disagreements=[])
            return super().generate(schema, instruction, data)
    monkeypatch.setattr('app.worker.providers', lambda c: (FixtureSearch(), Unsupported()))
    client.post('/tasks', json=task_payload(task_id='bad'))
    client.post('/tasks/bad/process')
    run_once(factory)
    assert client.get('/tasks/bad').json()['status'] == 'failed'
    assert client.get('/tasks/bad/lessons').json() == []


def test_lease_recovery_and_stale_worker_fencing(setup):
    client, factory, _ = setup
    client.post('/tasks', json=task_payload())
    client.post('/tasks/task-1/process')
    first = claim(factory)
    assert first and claim(factory) is None
    with factory.begin() as db:
        db.get(Job, 'task-1').lease_until = 0
    second = claim(factory)
    assert second and second[1] != first[1]
    process(*first, factory=factory)
    with factory() as db:
        assert db.get(Job, 'task-1').token == second[1]
        assert db.get(Job, 'task-1').status == 'running'
    process(*second, factory=factory)
    assert client.get('/tasks/task-1').json()['status'] == 'ready'


def test_scanned_pdf_fails_explicitly(setup):
    client, factory, _ = setup
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    data = io.BytesIO()
    writer.write(data)
    with pytest.raises(ValueError, match='scanned'):
        extract(data.getvalue(), 'application/pdf', 'scan.pdf', 20)
    file_id = client.post('/uploads', files={'file': ('scan.pdf', data.getvalue(), 'application/pdf')}).json()['file_id']
    create_process(setup, task_payload(purpose='exam', resources=[{'kind': 'file', 'value': file_id, 'role': 'syllabus'}]))
    status = client.get('/tasks/task-1').json()
    assert any('scanned' in warning for warning in status['research']['warnings'])
    assert client.get('/tasks/task-1/plan').json()['scope_status'] == 'provisional'


def test_prior_claim_not_demonstrated_and_deadline_respected(setup):
    client, _, _ = setup
    payload = task_payload()
    payload['prior_knowledge'] = [{'topic': 'Vectors and weighted sums', 'state': 'demonstrated', 'evidence': 'I read a page', 'evidence_type': 'self_report'}]
    payload['deadline'] = '2020-01-01T00:00:00Z'
    create_process(setup, payload)
    assert client.get('/tasks/task-1/plan').json()['planned_minutes'] == 0
    states = client.get('/tasks/task-1/progress').json()['topic_states']
    assert not any(s['state'] == 'demonstrated' for s in states)


def test_reduced_budget_does_not_recommend_unstarted_old_lesson(setup):
    client, _, _ = setup
    create_process(setup)
    assert client.get('/tasks/task-1/progress').json()['next_step']['action'] == 'study'
    assert client.patch('/tasks/task-1/time', json={'total_minutes': 1, 'session_minutes': 1}).status_code == 200
    assert client.get('/tasks/task-1/progress').json()['next_step']['action'] == 'review_budget'
    # The old artifact remains available for provenance; it is not part of the new recommendation.
    assert len(client.get('/tasks/task-1/lessons').json()) == 1
