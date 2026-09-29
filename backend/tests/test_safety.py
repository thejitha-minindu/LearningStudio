import pytest
from app.safety import PublicFetcher, ResourceError, allowed_path, resolve_public, validate_url
from app.config import Settings
from conftest import task_payload
from test_flow import create_process


@pytest.mark.parametrize('url', ['http://127.0.0.1', 'http://169.254.169.254/latest/meta-data', 'http://10.0.0.1', 'http://[::1]', 'http://[::ffff:127.0.0.1]', 'http://localhost', 'http://metadata.google.internal', 'ftp://example.com', 'file:///etc/passwd', 'http://example.com:22', 'https://user:pass@example.com', 'http://192.168.1.4', 'http://224.0.0.1', 'http://100.100.100.200'])
def test_unsafe_url_rejected(url):
    with pytest.raises(ResourceError):
        validate_url(url)


def test_dns_and_redirect_private_targets(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 80))])
    with pytest.raises(ResourceError, match='resolves'):
        resolve_public('https://public-looking.example')
    fetcher = PublicFetcher(Settings())
    monkeypatch.setattr(fetcher, '_robots_allowed', lambda url: None)
    monkeypatch.setattr(fetcher, '_request', lambda url: (302, {'location': 'http://169.254.169.254/'}, b''))
    with pytest.raises(ResourceError):
        fetcher.fetch('https://example.com')


def test_connection_uses_validated_ip_not_second_dns(monkeypatch):
    seen = []
    class FakeSocket:
        def close(self): pass
    class Response:
        status = 200
        def getheaders(self): return [('content-type', 'text/plain')]
        def read(self, n): return b''
    class Connection:
        def __init__(self, *a, **k): self.sock = None
        def request(self, *a, **k): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr('socket.getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 80))])
    monkeypatch.setattr('socket.create_connection', lambda address, timeout: seen.append(address) or FakeSocket())
    monkeypatch.setattr('http.client.HTTPConnection', Connection)
    PublicFetcher(Settings())._once('http://example.com/page')
    assert seen == [('93.184.216.34', 80)]


def test_local_paths_disabled_and_contained(tmp_path):
    root = tmp_path / 'allowed'
    root.mkdir()
    inside = root / 'notes.txt'
    inside.write_text('Allowed test notes', encoding='utf-8')
    outside = tmp_path / 'secret.txt'
    outside.write_text('Outside file', encoding='utf-8')
    with pytest.raises(ResourceError, match='disabled'):
        allowed_path(str(inside), '')
    assert allowed_path(str(inside), str(root)) == inside
    with pytest.raises(ResourceError, match='outside'):
        allowed_path(str(outside), str(root))


def test_ownership_on_tasks_files_lessons_passages_answers(setup):
    client, _, _ = setup
    create_process(setup)
    upload = client.post('/uploads', files={'file': ('notes.txt', b'Private notes belonging to Alice only.', 'text/plain')}).json()
    lesson = client.get('/tasks/task-1/lessons').json()[0]
    passage = lesson['sections'][0]['citations'][0]['passage_id']
    bob = {'X-Learner-ID': 'bob'}
    for path in ['', '/plan', '/lessons', '/sources', '/progress', f'/passages/{passage}']:
        assert client.get('/tasks/task-1' + path, headers=bob).status_code == 404
    for path in ['/process', '/next']:
        assert client.post('/tasks/task-1' + path, headers=bob).status_code == 404
    assert client.post('/tasks/task-1/answers', headers=bob, json={'attempt_id': 'steal', 'lesson_id': lesson['lesson_id'], 'question_id': 'check', 'answer': '-1'}).status_code == 404
    payload = task_payload(task_id='bob-task', resources=[{'kind': 'file', 'value': upload['file_id']}])
    payload['learner_id'] = 'bob'
    assert client.post('/tasks', headers=bob, json=payload).status_code == 404
    assert client.post('/tasks', headers=bob, json=task_payload('mismatch')).status_code == 403
    assert client.get('/tasks/task-1', headers={'X-Dev-Token': 'wrong'}).status_code == 401


def test_invalid_upload_and_resources(setup):
    client, _, cfg = setup
    assert client.post('/uploads', files={'file': ('program.exe', b'junk', 'application/octet-stream')}).status_code == 415
    assert client.post('/uploads', files={'file': ('bad.pdf', b'not a PDF', 'application/pdf')}).status_code == 422
    assert client.post('/uploads', files={'file': ('huge.txt', b'x' * (cfg.max_download_bytes + 1), 'text/plain')}).status_code == 413
    for ref in [{'kind': 'url', 'value': 'http://127.0.0.1'}, {'kind': 'local', 'value': 'C:/Windows/win.ini'}]:
        assert client.post('/tasks', json=task_payload(resources=[ref])).status_code == 422


def test_rate_limit_and_timezone_validation(setup, monkeypatch):
    client, _, cfg = setup
    payload = task_payload()
    payload['deadline'] = '2030-01-01T09:00:00'
    assert client.post('/tasks', json=payload).status_code == 422
    monkeypatch.setattr(cfg, 'rate_limit_per_minute', 1)
    response = client.post('/tasks', json=task_payload())
    assert response.status_code == 429
