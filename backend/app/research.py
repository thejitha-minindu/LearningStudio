import hashlib
import mimetypes
import re
from sqlalchemy import select
from .db import Cache, Source, Passage, Upload, now
from .extraction import extract
from .safety import PublicFetcher, ResourceError, allowed_path, validate_url


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()


def cached(db, key, seconds, fn):
    item = db.get(Cache, key)
    if item and item.expires_at > now():
        return item.data
    data = fn()
    if item:
        item.data, item.expires_at = data, now() + seconds
    else:
        db.add(Cache(key=key, data=data, expires_at=now() + seconds))
    db.flush()
    return data


def terms(text):
    return {x for x in re.findall(r'[\w]+', text.lower()) if len(x) > 3} - {'with', 'from', 'this', 'that', 'learn', 'understand', 'using', 'basics'}


def relevant(text, topic):
    text = text.lower()
    return any(keyword.lower() in text for keyword in topic['keywords'])


def stored_passages(db, task_id):
    rows = db.execute(select(Passage, Source).join(Source, Passage.source_id == Source.id).where(Passage.task_id == task_id)).all()
    return [{'source_id': s.id, 'passage_id': p.id, 'text': p.text, 'location': p.location, 'title': s.title, 'reference': s.reference, 'role': s.role, 'origin': s.origin} for p, s in rows]


class Research:
    def __init__(self, db, task, config, search):
        self.db, self.task, self.config, self.search = db, task, config, search
        self.fetcher = PublicFetcher(config)
        self.warnings, self.queries = [], []
        self.pages = 0
        self.seen = {s.reference for s in db.scalars(select(Source).where(Source.task_id == task.id))}

    def _extract_url(self, url):
        final, mime, data = self.fetcher.fetch(url)
        title, passages, warnings = extract(data, mime, final, self.config.max_pdf_pages)
        return {'reference': final, 'title': title, 'passages': passages, 'warnings': warnings, 'retrieved_at': now()}

    def ingest(self, ref, supplied=True):
        value, kind, role = ref['value'], ref['kind'], ref.get('role', 'reference')
        if value in self.seen:
            return
        self.seen.add(value)
        origin = 'supplied' if supplied else 'web'
        if kind == 'url' and value.startswith('fixture://'):
            from .fixtures import CORPUS
            key = value.removeprefix('fixture://')
            if supplied or self.config.provider_mode != 'fixture' or key not in CORPUS:
                raise ResourceError('Fixture references may only be produced by the explicit fixture provider.')
            item = CORPUS[key]
            result = {'reference': value, 'title': 'FIXTURE — ' + item['title'], 'passages': [{'location': 'authored fixture section', 'text': item['text']}], 'warnings': [], 'retrieved_at': now()}
            origin = 'fixture'
        elif kind == 'url':
            value = validate_url(value)
            result = cached(self.db, fingerprint(f'page:{self.task.owner}:{value}'), self.config.cache_seconds, lambda: self._extract_url(value))
        else:
            if kind == 'file':
                upload = self.db.get(Upload, value)
                if not upload or upload.owner != self.task.owner:
                    raise ResourceError('Uploaded file is missing or is not owned by this learner.')
                data, name, mime = upload.data, upload.name, upload.mime
            else:
                path = allowed_path(value, self.config.allowed_resource_dir)
                if path.stat().st_size > self.config.max_download_bytes:
                    raise ResourceError('Local file exceeds MAX_DOWNLOAD_BYTES.')
                with path.open('rb') as handle:
                    data = handle.read(self.config.max_download_bytes + 1)
                if len(data) > self.config.max_download_bytes:
                    raise ResourceError('Local file exceeds MAX_DOWNLOAD_BYTES.')
                name, mime = path.name, mimetypes.guess_type(path.name)[0] or ''
            title, passages, warnings = extract(data, mime, name, self.config.max_pdf_pages)
            result = {'reference': f'{kind}:{value}', 'title': title, 'passages': passages, 'warnings': warnings, 'retrieved_at': now()}
        self.warnings.extend(result['warnings'])
        digest = fingerprint(' '.join(x['text'] for x in result['passages']))
        if self.db.scalar(select(Source).where(Source.task_id == self.task.id, Source.digest == digest)):
            return
        source = Source(task_id=self.task.id, reference=result['reference'], title=result['title'], role=role, origin=origin, digest=digest, retrieved_at=result['retrieved_at'])
        self.db.add(source)
        self.db.flush()
        for chunk in result['passages']:
            self.db.add(Passage(task_id=self.task.id, source_id=source.id, **chunk))
        self.db.flush()

    def supplied(self):
        for ref in self.task.payload['resources']:
            try:
                self.ingest(ref)
            except ResourceError as error:
                self.warnings.append(f'Supplied {ref["role"]} resource could not be used: {error}')

    def run(self, topics):
        missing = []
        exhausted = False
        for topic in topics:
            evidence = stored_passages(self.db, self.task.id)
            # Syllabus headings establish scope, not instructional evidence.
            covered = any(p['role'] != 'syllabus' and relevant(p['text'], topic) for p in evidence)
            # Fixture lessons always require their explicit authored source.
            if self.config.provider_mode == 'fixture':
                covered = covered and any(p['reference'] == f'fixture://{topic["id"]}' for p in evidence)
            if covered:
                continue
            if len(self.queries) >= self.config.max_searches or self.pages >= self.config.max_pages:
                exhausted = True
                break
            query = f'{self.task.payload["objective"][:350]} {topic["title"]} {" ".join(topic["keywords"][:3])} tutorial worked example'
            self.queries.append(query)
            results = cached(self.db, fingerprint(f'search:{self.config.provider_mode}:{self.task.owner}:{query}'), self.config.cache_seconds, lambda: {'results': self.search.search(query)})['results']
            for result in results:
                if self.pages >= self.config.max_pages:
                    exhausted = True
                    break
                if result['url'] in self.seen:
                    continue
                hint = result['title'] + ' ' + result.get('snippet', '')
                if not any(relevant(hint, candidate) for candidate in topics):
                    continue
                self.pages += 1
                try:
                    self.ingest({'kind': 'url', 'value': result['url']}, supplied=False)
                except ResourceError as error:
                    self.warnings.append(f'Candidate skipped: {error}')
            self.db.flush()
        evidence = stored_passages(self.db, self.task.id)
        missing = [t['id'] for t in topics if not any(p['role'] != 'syllabus' and relevant(p['text'], t) for p in evidence)]
        return {'mode': self.config.provider_mode, 'queries': self.queries, 'pages_attempted': self.pages, 'warnings': self.warnings,
                'missing_topics': missing, 'coverage_method': 'Keyword coverage heuristic; not a semantic sufficiency guarantee.',
                'stop_reason': 'research_limit_reached' if exhausted or missing else 'topic_evidence_found',
                'live_research': self.config.provider_mode == 'live' and bool(self.queries)}
