"""HTTP demonstration against running API + worker; never starts an in-process worker."""
import argparse
import json
import os
from pathlib import Path
import time
import uuid
import httpx


def run(base, exam=False):
    root = Path(__file__).resolve().parents[1]
    headers = {'X-Learner-ID': 'demo-learner', 'X-Dev-Token': os.getenv('DEV_API_TOKEN', 'local-development-only')}
    with httpx.Client(base_url=base, headers=headers, timeout=120, trust_env=False) as client:
        health = client.get('/health').raise_for_status().json()
        payload = json.loads((root / 'examples' / ('database-exam.json' if exam else 'neural-networks.json')).read_text())
        payload['task_id'] = ('exam-' if exam else 'neural-') + uuid.uuid4().hex[:10]
        if exam:
            payload['resources'] = []
            for name, role in [('syllabus.txt', 'syllabus'), ('lecture-1-keys.pdf', 'lecture'), ('lecture-2-joins.pdf', 'lecture')]:
                path = root / 'examples' / name
                if not path.exists():
                    raise SystemExit('Run python examples/make_pdfs.py first.')
                result = client.post('/uploads', files={'file': (name, path.read_bytes())}).raise_for_status().json()
                payload['resources'].append({'kind': 'file', 'value': result['file_id'], 'role': role})
        client.post('/tasks', json=payload).raise_for_status()
        path = '/tasks/' + payload['task_id']
        client.post(path + '/process').raise_for_status()
        stop = time.monotonic() + 600
        while time.monotonic() < stop:
            status = client.get(path).raise_for_status().json()
            if status['status'] in ('ready', 'failed'):
                break
            time.sleep(2)
        else:
            raise SystemExit('Timed out. Is the separate persistent worker running?')
        if status['status'] == 'failed':
            raise SystemExit(status['error'])
        plan = client.get(path + '/plan').raise_for_status().json()
        lessons = client.get(path + '/lessons').raise_for_status().json()
        assert plan['planned_minutes'] <= plan['budget_minutes']
        assert lessons, 'No lesson fit the budget or available evidence.'
        lesson = lessons[0]
        citation = lesson['sections'][0]['citations'][0]
        evidence = client.get(path + '/passages/' + citation['passage_id']).raise_for_status().json()
        assert evidence['source_id'] == citation['source_id']
        if health['provider_mode'] == 'fixture':
            question = next(q for q in lesson['questions'] if q['kind'] == 'choice')
            answer = 'Unique and non-null' if exam else '-1'
            result = client.post(path + '/answers', json={'attempt_id': uuid.uuid4().hex, 'lesson_id': lesson['lesson_id'], 'question_id': question['id'], 'answer': answer}).raise_for_status().json()
        else:
            result = {'note': 'Live lesson generated; open the UI to answer it yourself.'}
        output = {'task_id': payload['task_id'], 'provider_mode': health['provider_mode'], 'scope_status': plan['scope_status'],
                  'planned_minutes': plan['planned_minutes'], 'source_count': len(client.get(path + '/sources').json()),
                  'citation_resolved': True, 'assessment': result, 'research': status['research']}
        print(json.dumps(output, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--exam', action='store_true')
    args = parser.parse_args()
    run(args.base, args.exam)
