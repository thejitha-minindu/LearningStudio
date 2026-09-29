import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.config import Settings, settings
from app.db import Base, get_db, make_engine
from app.main import app, rates


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, 'provider_mode', 'fixture')
    monkeypatch.setattr(cfg, 'dev_api_token', 'test-token')
    monkeypatch.setattr(cfg, 'rate_limit_per_minute', 10000)
    monkeypatch.setattr(cfg, 'allowed_resource_dir', '')
    rates.clear()
    engine = make_engine(f'sqlite:///{tmp_path / "test.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app, headers={'X-Learner-ID': 'alice', 'X-Dev-Token': 'test-token'}) as client:
        yield client, factory, cfg
    app.dependency_overrides.clear()
    engine.dispose()


def task_payload(task_id='task-1', purpose='long_term', resources=None, total=60):
    return {'task_id': task_id, 'learner_id': 'alice', 'long_term_goal': 'Build useful machine learning tools',
            'objective': 'Learn neural networks using Python', 'purpose': purpose,
            'session_minutes': 20, 'total_minutes': total, 'prior_knowledge': [], 'resources': resources or []}
