import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, LargeBinary, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def now():
    return datetime.now(timezone.utc).timestamp()


def uid():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    submission_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(default='created')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(default=now)


class Upload(Base):
    __tablename__ = 'uploads'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    mime: Mapped[str]
    data: Mapped[bytes] = mapped_column(LargeBinary)
    digest: Mapped[str]
    __table_args__ = (UniqueConstraint('owner', 'digest'),)


class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(index=True)
    reference: Mapped[str] = mapped_column(Text)
    title: Mapped[str]
    role: Mapped[str]
    origin: Mapped[str]
    retrieved_at: Mapped[float] = mapped_column(default=now)
    digest: Mapped[str]
    __table_args__ = (UniqueConstraint('task_id', 'digest'),)


class Passage(Base):
    __tablename__ = 'passages'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(index=True)
    source_id: Mapped[str] = mapped_column(index=True)
    location: Mapped[str]
    text: Mapped[str] = mapped_column(Text)


class Plan(Base):
    __tablename__ = 'plans'
    task_id: Mapped[str] = mapped_column(primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class Lesson(Base):
    __tablename__ = 'lessons'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(index=True)
    topic_id: Mapped[str]
    variant: Mapped[str] = mapped_column(default='standard')
    data: Mapped[dict] = mapped_column(JSON)
    audit: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('task_id', 'topic_id', 'variant'),)


class TopicState(Base):
    __tablename__ = 'topic_states'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(index=True)
    topic: Mapped[str]
    state: Mapped[str] = mapped_column(default='unknown')
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    last_assessed: Mapped[float | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint('owner', 'topic'),)


class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[str] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(index=True)
    owner: Mapped[str]
    lesson_id: Mapped[str]
    question_id: Mapped[str]
    answer: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(default=now)


class Job(Base):
    __tablename__ = 'jobs'
    task_id: Mapped[str] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(default='queued', index=True)
    token: Mapped[str] = mapped_column(default='')
    lease_until: Mapped[float] = mapped_column(default=0.0)
    attempts: Mapped[int] = mapped_column(default=0)
    kind: Mapped[str] = mapped_column(default='pipeline')
    topic_id: Mapped[str] = mapped_column(default='')


class Cache(Base):
    __tablename__ = 'cache'
    key: Mapped[str] = mapped_column(primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[float]


def make_engine(url):
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_pragmas(connection, _):
            connection.execute('PRAGMA journal_mode=WAL')
    return engine


engine = make_engine(settings().database_url)
Session = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with Session() as db:
        yield db
