import hashlib
import hmac
import json
import re
import threading
from collections import defaultdict, deque
from pathlib import Path
from time import monotonic
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .contracts import AnswerInput, ResourceRef, TaskInput, TimeUpdate
from .db import Attempt, Job, Lesson, Passage, Plan, Source, Task, TopicState, Upload, get_db
from .learning import build_plan, grade_answer, recommendation, topic_key, update_state
from .providers import ProviderError, providers
from .research import fingerprint
from .safety import ResourceError, allowed_path, resolve_public

app = FastAPI(title='Context-aware adaptive learning', version='0.1.0', description='Development identity only. This module does not schedule reminders or track activity.')
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(','), allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type', 'X-Learner-ID', 'X-Dev-Token'])
rates, rate_lock = defaultdict(deque), threading.Lock()


@app.middleware('http')
async def body_limit(request: Request, call_next):
    cap = settings().max_download_bytes + 65536 if request.url.path == '/uploads' else 100000
    try:
        if int(request.headers.get('content-length', 0)) > cap:
            return JSONResponse(status_code=413, content={'detail': 'Request exceeds the configured size limit.'})
    except ValueError:
        return JSONResponse(status_code=400, content={'detail': 'Invalid Content-Length.'})
    # Count streamed/chunked bodies as well, before multipart parsing can spool them to disk.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > cap:
            return JSONResponse(status_code=413, content={'detail': 'Request exceeds the configured size limit.'})
    request._body = bytes(body)
    return await call_next(request)


def identity(x_learner_id: str = Header(...), x_dev_token: str = Header(...)):
    if not settings().dev_api_token or not hmac.compare_digest(x_dev_token, settings().dev_api_token):
        raise HTTPException(401, 'Invalid development API token.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', x_learner_id):
        raise HTTPException(422, 'Invalid X-Learner-ID.')
    current = monotonic()
    with rate_lock:
        # Shared-token aggregate limit prevents bypass by inventing learner IDs.
        bucket = rates['development-token']
        while bucket and bucket[0] < current - 60:
            bucket.popleft()
        if len(bucket) >= settings().rate_limit_per_minute:
            raise HTTPException(429, 'Request rate limit reached. Wait one minute.', headers={'Retry-After': '60'})
        bucket.append(current)
    return x_learner_id


def owned(db, task_id, owner, lock=False):
    query = select(Task).where(Task.id == task_id, Task.owner == owner)
    if lock:
        query = query.with_for_update()
    task = db.scalar(query)
    if not task:
        raise HTTPException(404, 'Learning task not found.')
    return task


def validate_ref(db, ref, owner):
    try:
        if ref.kind == 'file':
            upload = db.get(Upload, ref.value)
            if not upload or upload.owner != owner:
                raise HTTPException(404, 'Uploaded resource not found.')
        elif ref.kind == 'url':
            resolve_public(ref.value)
        else:
            allowed_path(ref.value, settings().allowed_resource_dir)
    except ResourceError as error:
        raise HTTPException(422, str(error)) from None


def enqueue(db, task, kind='pipeline', topic_id='', retry=False):
    job = db.get(Job, task.id)
    if job and job.status in ('queued', 'running'):
        return
    if job:
        job.status, job.kind, job.topic_id, job.attempts = 'queued', kind, topic_id, 0
    else:
        db.add(Job(task_id=task.id, kind=kind, topic_id=topic_id))
    task.status, task.error = 'queued', None


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': str(exc)})


@app.exception_handler(IntegrityError)
async def concurrent_error(request, exc):
    return JSONResponse(status_code=409, content={'detail': 'Concurrent duplicate write. Retry the same request ID; the existing result will be returned.'})


@app.get('/health')
def health():
    return {'status': 'ok', 'provider_mode': settings().provider_mode, 'identity': 'development-only', 'fixture_domains': ['neural networks', 'databases']}


@app.post('/uploads', status_code=201)
async def upload_document(file: UploadFile, owner=Depends(identity), db: Session = Depends(get_db)):
    name = Path((file.filename or 'file').replace('\\', '/')).name[:200]
    suffix = Path(name).suffix.lower()
    mime = {'.pdf': 'application/pdf', '.txt': 'text/plain', '.html': 'text/html', '.htm': 'text/html'}.get(suffix)
    if not mime:
        raise HTTPException(415, 'Upload a text-based PDF, UTF-8 TXT or HTML file.')
    data = await file.read(settings().max_download_bytes + 1)
    await file.close()
    if len(data) > settings().max_download_bytes:
        raise HTTPException(413, 'File exceeds MAX_DOWNLOAD_BYTES.')
    if not data or (suffix == '.pdf' and not data.startswith(b'%PDF-')):
        raise HTTPException(422, 'File is empty or has an invalid PDF signature.')
    digest = hashlib.sha256(data).hexdigest()
    record = db.scalar(select(Upload).where(Upload.owner == owner, Upload.digest == digest))
    if not record:
        record = Upload(owner=owner, name=name, mime=mime, data=data, digest=digest)
        db.add(record)
        db.commit()
    return {'file_id': record.id, 'name': record.name, 'bytes': len(data)}


@app.post('/tasks', status_code=201)
def create_task(payload: TaskInput, owner=Depends(identity), db: Session = Depends(get_db)):
    if owner != payload.learner_id:
        raise HTTPException(403, 'learner_id must match the development identity.')
    data = payload.model_dump(mode='json')
    digest = fingerprint(json.dumps(data, sort_keys=True))
    existing = db.get(Task, payload.task_id)
    if existing:
        if existing.owner != owner:
            raise HTTPException(404, 'Learning task not found.')
        if existing.submission_hash != digest:
            raise HTTPException(409, 'task_id already exists with different input; use a new ID or a documented update endpoint.')
        return {'task_id': existing.id, 'status': existing.status, 'reused': True}
    for ref in payload.resources:
        validate_ref(db, ref, owner)
    task = Task(id=payload.task_id, owner=owner, payload=data, submission_hash=digest)
    db.add(task)
    db.commit()
    return {'task_id': task.id, 'status': task.status, 'reused': False}


@app.get('/tasks/{task_id}')
def get_task(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner)
    job = db.get(Job, task_id)
    return {'task': task.payload, 'status': task.status, 'error': task.error, 'research': task.report,
            'job': {'status': job.status, 'attempts': job.attempts, 'kind': job.kind} if job else None,
            'provider_mode': settings().provider_mode}


@app.post('/tasks/{task_id}/resources')
def add_resource(task_id: str, ref: ResourceRef, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner, lock=True)
    if task.status not in ('created', 'failed') or db.get(Plan, task_id):
        raise HTTPException(409, 'Add resources before processing. For an existing plan, create a new task with the revised scope.')
    validate_ref(db, ref, owner)
    resources = task.payload['resources']
    if ref.model_dump() not in resources:
        if len(resources) >= 12:
            raise HTTPException(422, 'At most 12 supplied resources are allowed.')
        task.payload = {**task.payload, 'resources': [*resources, ref.model_dump()]}
    db.commit()
    return {'resources': task.payload['resources']}


@app.post('/tasks/{task_id}/process', status_code=202)
def start(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner, lock=True)
    if task.status != 'ready':
        job = db.get(Job, task_id)
        enqueue(db, task, job.kind if job and job.status == 'failed' else 'pipeline', job.topic_id if job and job.status == 'failed' else '')
        db.commit()
    return {'task_id': task.id, 'status': task.status}


@app.get('/tasks/{task_id}/plan')
def get_plan(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    owned(db, task_id, owner)
    plan = db.get(Plan, task_id)
    if not plan:
        raise HTTPException(404, 'Plan is not available yet.')
    return plan.data


def public_lesson(lesson):
    data = dict(lesson.data)
    data['questions'] = [{k: v for k, v in q.items() if k != 'answer'} for q in data['questions']]
    return {'lesson_id': lesson.id, 'topic_id': lesson.topic_id, 'variant': lesson.variant, **data, 'support_audit': lesson.audit}


@app.get('/tasks/{task_id}/lessons')
def lessons(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    owned(db, task_id, owner)
    return [public_lesson(lesson) for lesson in db.scalars(select(Lesson).where(Lesson.task_id == task_id))]


@app.get('/tasks/{task_id}/sources')
def sources(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    owned(db, task_id, owner)
    return [{'source_id': s.id, 'reference': s.reference, 'title': s.title, 'role': s.role, 'origin': s.origin, 'retrieved_at': s.retrieved_at} for s in db.scalars(select(Source).where(Source.task_id == task_id))]


@app.get('/tasks/{task_id}/passages/{passage_id}')
def passage(task_id: str, passage_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    owned(db, task_id, owner)
    item = db.get(Passage, passage_id)
    if not item or item.task_id != task_id:
        raise HTTPException(404, 'Passage not found.')
    source = db.get(Source, item.source_id)
    return {'passage_id': item.id, 'source_id': item.source_id, 'text': item.text, 'location': item.location, 'reference': source.reference, 'title': source.title, 'retrieved_at': source.retrieved_at, 'origin': source.origin}


@app.post('/tasks/{task_id}/answers')
def submit_answer(task_id: str, payload: AnswerInput, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner, lock=True)
    if task.status != 'ready':
        raise HTTPException(409, 'Wait for processing to finish before submitting an answer.')
    previous = db.get(Attempt, payload.attempt_id)
    if previous:
        if previous.owner != owner or previous.task_id != task_id:
            raise HTTPException(404, 'Attempt not found.')
        if (previous.lesson_id, previous.question_id, previous.answer) != (payload.lesson_id, payload.question_id, payload.answer):
            raise HTTPException(409, 'attempt_id already exists with a different answer.')
        return {'result': previous.result, 'next_step': recommendation(db, task), 'reused': True}
    lesson = db.get(Lesson, payload.lesson_id)
    if not lesson or lesson.task_id != task_id:
        raise HTTPException(404, 'Lesson not found.')
    question = next((q for q in lesson.data['questions'] if q['id'] == payload.question_id), None)
    if not question:
        raise HTTPException(404, 'Question not found.')
    if question['kind'] == 'choice' and payload.answer not in question['options']:
        raise HTTPException(422, 'Select one of the provided options.')
    _, generator = providers(settings())
    result = grade_answer(question, payload.answer, generator)
    db.add(Attempt(id=payload.attempt_id, task_id=task_id, owner=owner, lesson_id=lesson.id, question_id=question['id'], answer=payload.answer, result=result))
    state = update_state(db, task, lesson, question, result, payload.attempt_id)
    db.flush()
    next_step = recommendation(db, task)
    plan = db.get(Plan, task_id)
    plan.data = build_plan(db, task, plan.data['curriculum'], task.report, next_step.get('topic_id') if next_step['action'] == 'support' else None)
    db.commit()
    return {'result': result, 'topic_state': {'state': state.state, 'confidence': state.confidence}, 'next_step': recommendation(db, task), 'reused': False}


@app.post('/tasks/{task_id}/next', status_code=202)
def next_lesson(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner, lock=True)
    if task.status != 'ready':
        raise HTTPException(409, 'Wait for the current job or retry a failed job first.')
    step = recommendation(db, task)
    if step['action'] in ('support', 'generate'):
        plan = db.get(Plan, task_id)
        if not any(t['id'] == step['topic_id'] and t['variant'] == step['variant'] for t in plan.data['topics']):
            return {'action': 'review_budget', 'reason': 'The recommended lesson does not fit the remaining time. Increase the budget.'}
        enqueue(db, task, 'support' if step['action'] == 'support' else 'lesson', step['topic_id'])
        db.commit()
    return step


@app.patch('/tasks/{task_id}/time')
def update_time(task_id: str, payload: TimeUpdate, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner, lock=True)
    if task.status not in ('created', 'ready', 'failed'):
        raise HTTPException(409, 'Wait for processing before changing the time budget.')
    task.payload = {**task.payload, **payload.model_dump()}
    plan = db.get(Plan, task_id)
    if plan:
        step = recommendation(db, task)
        plan.data = build_plan(db, task, plan.data['curriculum'], task.report, step.get('topic_id') if step['action'] == 'support' else None)
    db.commit()
    return plan.data if plan else {'task': task.payload}


@app.get('/tasks/{task_id}/progress')
def progress(task_id: str, owner=Depends(identity), db: Session = Depends(get_db)):
    task = owned(db, task_id, owner)
    plan = db.get(Plan, task_id)
    all_states = list(db.scalars(select(TopicState).where(TopicState.owner == owner)))
    attempts = list(db.scalars(select(Attempt).where(Attempt.task_id == task_id).order_by(Attempt.created_at)))
    if plan and 'curriculum' in plan.data and 'topics' in plan.data['curriculum']:
        relevant_keys = {topic_key(t['title']) for t in plan.data['curriculum']['topics']}
        states = [s for s in all_states if s.topic in relevant_keys or any(e.get('task_id') == task_id for e in s.evidence)]
    elif task.payload.get('prior_knowledge'):
        relevant_keys = {topic_key(p['topic']) for p in task.payload['prior_knowledge']}
        states = [s for s in all_states if s.topic in relevant_keys or any(e.get('task_id') == task_id for e in s.evidence)]
    else:
        states = [s for s in all_states if any(e.get('task_id') == task_id for e in s.evidence)]
    return {'topic_states': [{'topic': s.topic, 'state': s.state, 'confidence': s.confidence, 'last_assessed': s.last_assessed, 'evidence': s.evidence} for s in states],
            'attempts': [{'attempt_id': a.id, 'lesson_id': a.lesson_id, 'question_id': a.question_id, 'answer': a.answer, 'result': a.result} for a in attempts],
            'next_step': recommendation(db, task), 'mastery_policy': 'At least three distinct, reliable successful questions including transfer; reading and repeated easy answers do not establish mastery.'}
