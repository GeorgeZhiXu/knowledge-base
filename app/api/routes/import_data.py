"""Bulk import routes for populating knowledge base data efficiently."""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import Lesson, Word, WordLesson

router = APIRouter()


# --- Request schemas ---

class WordImport(BaseModel):
    word: str
    pinyin: str = ""
    requirement: str = "recognize"

class LessonImport(BaseModel):
    lesson_number: int
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    words: list[WordImport] = []

class UnitImport(BaseModel):
    unit_number: int
    title: str
    lessons: list[LessonImport] = []

class TextbookImport(BaseModel):
    grade: int
    volume: int
    units: list[UnitImport] = []

class FullImport(BaseModel):
    """Import an entire textbook with all units, lessons, and words."""
    textbook: TextbookImport

class LessonDataImport(BaseModel):
    """Import words for an existing lesson."""
    lesson_id: int
    words: list[WordImport] = []


async def _import_words(
    db: AsyncSession,
    lesson_id: int,
    words: list[WordImport],
) -> dict:
    stats = {"words": 0, "word_lessons": 0}

    for i, w in enumerate(words):
        existing = await db.exec(select(Word).where(Word.word == w.word))
        if not existing.one_or_none():
            db.add(Word(word=w.word, pinyin=w.pinyin))
            stats["words"] += 1

        existing_wl = await db.exec(
            select(WordLesson)
            .where(WordLesson.word == w.word)
            .where(WordLesson.lesson_id == lesson_id)
            .where(WordLesson.requirement == w.requirement)
        )
        if not existing_wl.one_or_none():
            db.add(WordLesson(
                word=w.word, lesson_id=lesson_id,
                requirement=w.requirement, sort_order=i,
            ))
            stats["word_lessons"] += 1

    return stats


@router.post("/import/textbook")
async def import_textbook(data: FullImport, db: AsyncSession = Depends(get_session)):
    """Import an entire textbook with all units, lessons, and words."""
    tb = data.textbook
    totals = {"lessons": 0, "words": 0, "word_lessons": 0}

    for unit_data in tb.units:
        for lesson_data in unit_data.lessons:
            lesson = Lesson(
                grade=tb.grade, volume=tb.volume,
                unit_number=unit_data.unit_number, unit_title=unit_data.title,
                lesson_number=lesson_data.lesson_number,
                title=lesson_data.title, page_start=lesson_data.page_start,
                page_end=lesson_data.page_end,
            )
            db.add(lesson)
            await db.flush()
            totals["lessons"] += 1

            stats = await _import_words(db, lesson.id, lesson_data.words)
            for k, v in stats.items():
                totals[k] += v

    await db.commit()
    return {"status": "ok", **totals}


@router.post("/import/lesson")
async def import_lesson_data(data: LessonDataImport, db: AsyncSession = Depends(get_session)):
    """Import words for an existing lesson."""
    stats = await _import_words(db, data.lesson_id, data.words)
    await db.commit()
    return {"status": "ok", **stats}


class FrequencyEntry(BaseModel):
    word: str
    pinyin: str = ""
    standard_level: Optional[int] = None
    cumulative_percent: Optional[float] = None

class FrequencyImport(BaseModel):
    words: list[FrequencyEntry]

@router.post("/import/frequency")
async def import_frequency_data(data: FrequencyImport, db: AsyncSession = Depends(get_session)):
    """Import word frequency data. Creates new words or updates existing ones."""
    created = 0
    updated = 0
    for entry in data.words:
        result = await db.exec(select(Word).where(Word.word == entry.word))
        word = result.one_or_none()
        if word:
            if entry.standard_level is not None:
                word.standard_level = entry.standard_level
            if entry.cumulative_percent is not None:
                word.cumulative_percent = entry.cumulative_percent
            if entry.pinyin and not word.pinyin:
                word.pinyin = entry.pinyin
            db.add(word)
            updated += 1
        else:
            db.add(Word(
                word=entry.word, pinyin=entry.pinyin,
                standard_level=entry.standard_level,
                cumulative_percent=entry.cumulative_percent,
            ))
            created += 1
    await db.commit()
    return {"status": "ok", "created": created, "updated": updated}
