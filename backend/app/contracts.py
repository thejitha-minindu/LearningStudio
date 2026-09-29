import re
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Purpose(str, Enum):
    long_term = 'long_term'
    exam = 'exam'
    practical = 'practical'


class Knowledge(Contract):
    topic: str = Field(min_length=2, max_length=150)
    state: Literal['unknown', 'needs_support', 'developing', 'demonstrated'] = 'unknown'
    evidence: str = Field('', max_length=2000)
    evidence_type: Literal['self_report', 'diagnostic', 'exercise'] = 'self_report'


class ResourceRef(Contract):
    kind: Literal['url', 'file', 'local']
    value: str = Field(min_length=1, max_length=2048)
    role: Literal['reference', 'syllabus', 'lecture'] = 'reference'


class Preferences(Contract):
    language: str = Field('English', min_length=2, max_length=40)
    depth: Literal['brief', 'balanced', 'deep'] = 'balanced'


class TaskInput(Contract):
    task_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    learner_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    long_term_goal: str = Field(min_length=3, max_length=2000)
    objective: str = Field(min_length=5, max_length=2000)
    purpose: Purpose
    deadline: datetime | None = None
    total_minutes: int | None = Field(None, ge=1, le=100000)
    session_minutes: int = Field(25, ge=1, le=240)
    prior_knowledge: list[Knowledge] = Field(default_factory=list, max_length=30)
    resources: list[ResourceRef] = Field(default_factory=list, max_length=12)
    preferences: Preferences = Field(default_factory=Preferences)

    @model_validator(mode='after')
    def timezone_required(self):
        if self.deadline and self.deadline.tzinfo is None:
            raise ValueError('deadline must include a timezone, for example +05:30')
        return self


class Topic(Contract):
    id: str = Field(pattern=r'^[a-z0-9_-]{1,60}$')
    title: str = Field(min_length=2, max_length=150)
    objective: str = Field(min_length=5, max_length=500)
    prerequisites: list[str] = Field(default_factory=list, max_length=6)
    keywords: list[str] = Field(min_length=1, max_length=8)
    estimated_minutes: int = Field(ge=5, le=120)
    practice: str = Field(min_length=5, max_length=500)

    @field_validator('id', mode='before')
    @classmethod
    def sanitize_id(cls, v):
        if isinstance(v, str):
            clean = re.sub(r'[^a-z0-9_-]+', '-', v.strip().lower()).strip('-')
            return clean[:60] or 'topic'
        return v

    @field_validator('estimated_minutes', mode='before')
    @classmethod
    def clamp_minutes(cls, v):
        try:
            return max(5, min(int(v), 120))
        except (ValueError, TypeError):
            return 25

    @field_validator('keywords', mode='before')
    @classmethod
    def trim_keywords(cls, v):
        if isinstance(v, list):
            res = [str(k).strip() for k in v[:8] if str(k).strip()]
            return res if res else ['core']
        return v

    @field_validator('prerequisites', mode='before')
    @classmethod
    def trim_prerequisites(cls, v):
        if isinstance(v, list):
            return [str(p).strip() for p in v[:6] if str(p).strip()]
        return v


class Curriculum(Contract):
    topics: list[Topic] = Field(min_length=1, max_length=6)
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    scope_status: Literal['supplied', 'provisional', 'not_applicable']

    @field_validator('topics', mode='before')
    @classmethod
    def trim_topics(cls, v):
        if isinstance(v, list) and len(v) > 6:
            return v[:6]
        return v

    @field_validator('assumptions', mode='before')
    @classmethod
    def trim_assumptions(cls, v):
        if isinstance(v, list) and len(v) > 10:
            return v[:10]
        return v

    @model_validator(mode='after')
    def ordered(self):
        seen = set()
        for idx, topic in enumerate(self.topics):
            if topic.id in seen:
                topic.id = f"{topic.id[:50]}-{idx+1}"
            seen.add(topic.id)
            topic.prerequisites = [p for p in topic.prerequisites if p in seen and p != topic.id]
        return self


class Citation(Contract):
    source_id: str
    passage_id: str

    @field_validator('source_id', 'passage_id', mode='before')
    @classmethod
    def clean_id(cls, v):
        if isinstance(v, str):
            return v.strip().replace('-', '').lower()
        return str(v) if v is not None else ''


class Section(Contract):
    heading: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=10, max_length=6000)
    citations: list[Citation] = Field(min_length=1, max_length=8)


class Question(Contract):
    id: str = Field(pattern=r'^[a-z0-9_-]{1,60}$')
    topic_id: str
    kind: Literal['choice', 'short_text']
    prompt: str = Field(min_length=5, max_length=1500)
    options: list[str] = Field(default_factory=list, max_length=6)
    answer: str = Field(min_length=1, max_length=2000)
    rubric: list[str] = Field(min_length=1, max_length=6)
    difficulty: Literal['recall', 'application', 'transfer']
    citations: list[Citation] = Field(min_length=1, max_length=6)

    @field_validator('id', mode='before')
    @classmethod
    def sanitize_id(cls, v):
        if isinstance(v, str):
            clean = re.sub(r'[^a-z0-9_-]+', '-', v.strip().lower()).strip('-')
            return clean[:60] or 'question'
        return v

    @field_validator('options', mode='before')
    @classmethod
    def trim_options(cls, v):
        if isinstance(v, list) and len(v) > 6:
            return v[:6]
        return v

    @field_validator('rubric', mode='before')
    @classmethod
    def trim_rubric(cls, v):
        if isinstance(v, list) and len(v) > 6:
            return v[:6]
        return v

    @model_validator(mode='after')
    def valid_choice(self):
        if self.kind == 'choice':
            if len(self.options) < 2:
                self.options = [self.answer, 'Alternative option'] if self.answer else ['Option A', 'Option B']
            if self.answer not in self.options:
                self.options.append(self.answer)
        return self


class LessonContent(Contract):
    title: str
    objectives: list[str] = Field(min_length=1, max_length=5)
    prerequisites: list[str] = Field(default_factory=list, max_length=6)
    sections: list[Section] = Field(min_length=2, max_length=6)
    questions: list[Question] = Field(min_length=2, max_length=4)
    limitations: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('objectives', mode='before')
    @classmethod
    def trim_objectives(cls, v):
        if isinstance(v, list) and len(v) > 5:
            return v[:5]
        return v

    @field_validator('prerequisites', mode='before')
    @classmethod
    def trim_prereqs(cls, v):
        if isinstance(v, list) and len(v) > 6:
            return v[:6]
        return v

    @field_validator('sections', mode='before')
    @classmethod
    def trim_sections(cls, v):
        if isinstance(v, list) and len(v) > 6:
            return v[:6]
        return v

    @field_validator('questions', mode='before')
    @classmethod
    def trim_questions(cls, v):
        if isinstance(v, list) and len(v) > 4:
            return v[:4]
        return v


class Grade(Contract):
    score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    feedback: str = Field(min_length=5, max_length=2500)
    criteria_met: list[str] = Field(default_factory=list, max_length=6)

    @field_validator('score', 'confidence', mode='before')
    @classmethod
    def clamp_float(cls, v):
        try:
            return max(0.0, min(float(v), 1.0))
        except (ValueError, TypeError):
            return 0.5


class Finding(Contract):
    description: str
    citations: list[Citation] = Field(min_length=1, max_length=8)


class Audit(Contract):
    support: Literal['supported', 'uncertain', 'unsupported']
    explanation: str
    disagreements: list[Finding] = Field(default_factory=list, max_length=6)


class AnswerInput(Contract):
    attempt_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    lesson_id: str
    question_id: str
    answer: str = Field(min_length=1, max_length=4000)


class TimeUpdate(Contract):
    total_minutes: int = Field(ge=1, le=100000)
    session_minutes: int = Field(ge=1, le=240)
