from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


# --- Curriculum ---

class Lesson(SQLModel, table=True):
    __tablename__ = "lessons"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    grade: int = Field(index=True)           # 1-6
    volume: int = Field(index=True)          # 1=上册, 2=下册
    unit_number: int = Field(default=0)
    unit_title: Optional[str] = Field(default=None, max_length=200)
    lesson_number: int = Field(default=0)
    title: str = Field(max_length=200)
    page_start: Optional[int] = None
    page_end: Optional[int] = None


# --- Requirement labels (not a DB table, just a mapping) ---
REQUIREMENT_LABELS = {"recognize": "认识", "read": "会读", "write": "会写", "recite": "背诵"}


# --- Chinese-specific tables ---

class Character(SQLModel, table=True):
    __tablename__ = "characters"
    character: str = Field(primary_key=True, max_length=1)
    pinyin: str = Field(max_length=50, default="")
    standard_level: Optional[int] = Field(default=None)  # 《通用规范汉字表》: 1=常用(top 3500), 2=次常用(3501-6500), 3=rare(6501+)
    cumulative_percent: Optional[float] = Field(default=None)  # cumulative text coverage %


class CharacterLesson(SQLModel, table=True):
    __tablename__ = "character_lessons"
    character: str = Field(foreign_key="characters.character", max_length=1, primary_key=True)
    lesson_id: UUID = Field(foreign_key="lessons.id", primary_key=True)
    requirement: str = Field(max_length=20, primary_key=True)  # 'recognize' or 'write'
    sort_order: int = Field(default=0)


class Phrase(SQLModel, table=True):
    __tablename__ = "phrases"
    phrase: str = Field(primary_key=True, max_length=100)
    pinyin: str = Field(max_length=200, default="")
    meaning: Optional[str] = Field(default=None, max_length=500)
    frequency_rank: Optional[int] = Field(default=None, index=True)
    frequency_count: Optional[int] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)


class PhraseLesson(SQLModel, table=True):
    __tablename__ = "phrase_lessons"
    phrase: str = Field(foreign_key="phrases.phrase", primary_key=True)
    lesson_id: UUID = Field(foreign_key="lessons.id", primary_key=True)
    sort_order: int = Field(default=0)


# --- Learner activity tracking ---

class TestSession(SQLModel, table=True):
    __tablename__ = "test_sessions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    learner: str = Field(max_length=100, index=True)  # username from auth system
    lesson_id: Optional[UUID] = Field(default=None, foreign_key="lessons.id")
    title: Optional[str] = Field(default=None, max_length=200)
    tested_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = Field(default=None, max_length=500)


class TestResult(SQLModel, table=True):
    __tablename__ = "test_results"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    learner: str = Field(max_length=100, index=True)  # username from auth system
    session_id: Optional[UUID] = Field(default=None, foreign_key="test_sessions.id")
    character: str = Field(foreign_key="characters.character", max_length=1, index=True)
    skill: str = Field(max_length=20)  # "read" or "write"
    passed: bool = Field(default=False)
    tested_at: datetime = Field(default_factory=datetime.utcnow)
