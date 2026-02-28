from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


# --- Requirement labels (not a DB table, just a mapping) ---
REQUIREMENT_LABELS = {"recognize": "认识", "read": "会读", "write": "会写", "recite": "背诵"}


# --- Curriculum ---

class Lesson(SQLModel, table=True):
    __tablename__ = "lessons"
    id: Optional[int] = Field(default=None, primary_key=True)
    grade: int = Field(index=True)           # 1-6
    volume: int = Field(index=True)          # 1=上册, 2=下册
    unit_number: int = Field(default=0)
    unit_title: Optional[str] = Field(default=None, max_length=200)
    lesson_number: int = Field(default=0)
    title: str = Field(max_length=200)
    page_start: Optional[int] = None
    page_end: Optional[int] = None


# --- Words (characters + phrases unified) ---

class Word(SQLModel, table=True):
    __tablename__ = "words"
    word: str = Field(primary_key=True, max_length=100)  # single char "人" or phrase "人民"
    pinyin: str = Field(max_length=200, default="")
    meaning: Optional[str] = Field(default=None, max_length=500)
    standard_level: Optional[int] = Field(default=None)  # 《通用规范汉字表》: 1=常用, 2=次常用, 3=rare
    cumulative_percent: Optional[float] = Field(default=None)  # cumulative text coverage %
    radical: Optional[str] = Field(default=None, max_length=10)  # 部首, e.g. 氵
    decomposition: Optional[str] = Field(default=None, max_length=100)  # IDS, e.g. ⿰氵可
    etymology_type: Optional[str] = Field(default=None, max_length=20)  # pictographic/ideographic/pictophonetic
    phonetic: Optional[str] = Field(default=None, max_length=10)  # phonetic component, e.g. 可
    semantic: Optional[str] = Field(default=None, max_length=10)  # semantic component, e.g. 氵


class WordLesson(SQLModel, table=True):
    __tablename__ = "word_lessons"
    word: str = Field(foreign_key="words.word", primary_key=True)
    lesson_id: int = Field(foreign_key="lessons.id", primary_key=True)
    requirement: str = Field(max_length=20, primary_key=True)  # 'recognize' or 'write'
    sort_order: int = Field(default=0)


# --- Learner activity tracking ---

class TestResult(SQLModel, table=True):
    __tablename__ = "test_results"
    id: Optional[int] = Field(default=None, primary_key=True)
    learner: str = Field(max_length=100, index=True)
    word: str = Field(foreign_key="words.word", max_length=100, index=True)
    skill: str = Field(max_length=20)  # "read" or "write"
    passed: bool = Field(default=False)
    tested_at: datetime = Field(default_factory=datetime.utcnow)
    session_title: Optional[str] = Field(default=None, max_length=200)
    session_notes: Optional[str] = Field(default=None, max_length=500)
