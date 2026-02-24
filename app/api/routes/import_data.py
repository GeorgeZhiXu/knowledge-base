"""Bulk import routes for populating knowledge base data efficiently."""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import (
    Subject, Textbook, Unit, Lesson,
    Character, CharacterLesson, RequirementType,
    Phrase, PhraseCharacter, PhraseLesson,
)

router = APIRouter()


# --- Request schemas ---

class CharacterImport(BaseModel):
    character: str
    pinyin: str = ""
    requirement: str = "recognize"

class PhraseImport(BaseModel):
    phrase: str
    pinyin: str = ""
    meaning: Optional[str] = None

class LessonImport(BaseModel):
    lesson_number: int
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    characters: list[CharacterImport] = []
    phrases: list[PhraseImport] = []

class UnitImport(BaseModel):
    unit_number: int
    title: str
    lessons: list[LessonImport] = []

class TextbookImport(BaseModel):
    publisher: str = "人教版"
    grade: int
    volume: int
    name: str
    units: list[UnitImport] = []

class FullImport(BaseModel):
    """Import an entire textbook with all units, lessons, characters, and phrases."""
    subject_code: str = "chinese"
    subject_name: str = "语文"
    textbook: TextbookImport

class LessonDataImport(BaseModel):
    """Import characters and phrases for an existing lesson."""
    lesson_id: UUID
    characters: list[CharacterImport] = []
    phrases: list[PhraseImport] = []


async def _get_or_create_subject(db: AsyncSession, code: str, name: str) -> Subject:
    result = await db.exec(select(Subject).where(Subject.code == code))
    subject = result.one_or_none()
    if not subject:
        subject = Subject(code=code, name=name)
        db.add(subject)
        await db.flush()
    return subject


async def _get_requirement_map(db: AsyncSession) -> dict[str, UUID]:
    result = await db.exec(select(RequirementType))
    return {rt.code: rt.id for rt in result.all()}


async def _import_characters_and_phrases(
    db: AsyncSession,
    lesson_id: UUID,
    characters: list[CharacterImport],
    phrases: list[PhraseImport],
    req_map: dict[str, UUID],
) -> dict:
    stats = {"characters": 0, "character_lessons": 0, "phrases": 0, "phrase_lessons": 0}

    for i, ch in enumerate(characters):
        # Create or get character
        existing = await db.exec(select(Character).where(Character.character == ch.character))
        if not existing.one_or_none():
            db.add(Character(
                character=ch.character, pinyin=ch.pinyin,
            ))
            stats["characters"] += 1

        # Link to lesson
        req_id = req_map.get(ch.requirement)
        if req_id:
            existing_cl = await db.exec(
                select(CharacterLesson)
                .where(CharacterLesson.character == ch.character)
                .where(CharacterLesson.lesson_id == lesson_id)
                .where(CharacterLesson.requirement_id == req_id)
            )
            if not existing_cl.one_or_none():
                db.add(CharacterLesson(
                    character=ch.character, lesson_id=lesson_id,
                    requirement_id=req_id, sort_order=i,
                ))
                stats["character_lessons"] += 1

    for i, ph in enumerate(phrases):
        existing = await db.exec(select(Phrase).where(Phrase.phrase == ph.phrase))
        phrase = existing.one_or_none()
        if not phrase:
            phrase = Phrase(phrase=ph.phrase, pinyin=ph.pinyin, meaning=ph.meaning)
            db.add(phrase)
            await db.flush()
            stats["phrases"] += 1

            # Auto-link phrase characters
            for j, ch_str in enumerate(ph.phrase):
                ch_exists = await db.exec(select(Character).where(Character.character == ch_str))
                if ch_exists.one_or_none():
                    db.add(PhraseCharacter(phrase_id=phrase.id, character=ch_str, position=j))

        # Link to lesson
        existing_pl = await db.exec(
            select(PhraseLesson)
            .where(PhraseLesson.phrase_id == phrase.id)
            .where(PhraseLesson.lesson_id == lesson_id)
        )
        if not existing_pl.one_or_none():
            db.add(PhraseLesson(phrase_id=phrase.id, lesson_id=lesson_id, sort_order=i))
            stats["phrase_lessons"] += 1

    return stats


@router.post("/import/textbook")
async def import_textbook(data: FullImport, db: AsyncSession = Depends(get_session)):
    """Import an entire textbook with all units, lessons, characters, and phrases.

    Example:
    ```json
    {
      "subject_code": "chinese",
      "subject_name": "语文",
      "textbook": {
        "publisher": "人教版",
        "grade": 1,
        "volume": 1,
        "name": "一年级上册",
        "units": [
          {
            "unit_number": 1,
            "title": "第一单元",
            "lessons": [
              {
                "lesson_number": 1,
                "title": "天地人",
                "characters": [
                  {"character": "天", "pinyin": "tiān", "requirement": "recognize"},
                  {"character": "地", "pinyin": "dì", "requirement": "recognize"},
                  {"character": "人", "pinyin": "rén", "requirement": "write"}
                ],
                "phrases": [
                  {"phrase": "天地", "pinyin": "tiān dì"},
                  {"phrase": "人民", "pinyin": "rén mín", "meaning": "people"}
                ]
              }
            ]
          }
        ]
      }
    }
    ```
    """
    req_map = await _get_requirement_map(db)
    subject = await _get_or_create_subject(db, data.subject_code, data.subject_name)

    tb = data.textbook
    textbook = Textbook(
        subject_id=subject.id, publisher=tb.publisher,
        grade=tb.grade, volume=tb.volume, name=tb.name,
    )
    db.add(textbook)
    await db.flush()

    totals = {"units": 0, "lessons": 0, "characters": 0, "character_lessons": 0,
              "phrases": 0, "phrase_lessons": 0}

    for unit_data in tb.units:
        unit = Unit(textbook_id=textbook.id, unit_number=unit_data.unit_number, title=unit_data.title)
        db.add(unit)
        await db.flush()
        totals["units"] += 1

        for lesson_data in unit_data.lessons:
            lesson = Lesson(
                unit_id=unit.id, lesson_number=lesson_data.lesson_number,
                title=lesson_data.title, page_start=lesson_data.page_start,
                page_end=lesson_data.page_end,
            )
            db.add(lesson)
            await db.flush()
            totals["lessons"] += 1

            stats = await _import_characters_and_phrases(
                db, lesson.id, lesson_data.characters, lesson_data.phrases, req_map,
            )
            for k, v in stats.items():
                totals[k] += v

    await db.commit()
    return {
        "status": "ok",
        "textbook_id": str(textbook.id),
        "subject_id": str(subject.id),
        **totals,
    }


@router.post("/import/lesson")
async def import_lesson_data(data: LessonDataImport, db: AsyncSession = Depends(get_session)):
    """Import characters and phrases for an existing lesson."""
    req_map = await _get_requirement_map(db)
    stats = await _import_characters_and_phrases(
        db, data.lesson_id, data.characters, data.phrases, req_map,
    )
    await db.commit()
    return {"status": "ok", **stats}


class FrequencyEntry(BaseModel):
    character: str
    pinyin: str = ""
    standard_level: int = 1
    cumulative_percent: Optional[float] = None

class FrequencyImport(BaseModel):
    characters: list[FrequencyEntry]

@router.post("/import/frequency")
async def import_frequency_data(data: FrequencyImport, db: AsyncSession = Depends(get_session)):
    """Import character standard levels. Creates new characters or updates existing ones."""
    created = 0
    updated = 0
    for entry in data.characters:
        result = await db.exec(
            select(Character).where(Character.character == entry.character)
        )
        char = result.one_or_none()
        if char:
            char.standard_level = entry.standard_level
            if entry.cumulative_percent is not None:
                char.cumulative_percent = entry.cumulative_percent
            if entry.pinyin and not char.pinyin:
                char.pinyin = entry.pinyin
            db.add(char)
            updated += 1
        else:
            db.add(Character(
                character=entry.character,
                pinyin=entry.pinyin,
                standard_level=entry.standard_level,
                cumulative_percent=entry.cumulative_percent,
            ))
            created += 1
    await db.commit()
    return {"status": "ok", "created": created, "updated": updated}


class PhraseFrequencyEntry(BaseModel):
    phrase: str
    frequency_rank: int
    frequency_count: Optional[int] = None

class PhraseFrequencyImport(BaseModel):
    phrases: list[PhraseFrequencyEntry]

@router.post("/import/phrase-frequency")
async def import_phrase_frequency(data: PhraseFrequencyImport, db: AsyncSession = Depends(get_session)):
    """Import phrase frequency rankings. Creates new phrases or updates existing ones."""
    created = 0
    updated = 0
    for entry in data.phrases:
        result = await db.exec(
            select(Phrase).where(Phrase.phrase == entry.phrase)
        )
        phrase = result.first()
        if phrase:
            phrase.frequency_rank = entry.frequency_rank
            if entry.frequency_count is not None:
                phrase.frequency_count = entry.frequency_count
            db.add(phrase)
            updated += 1
        else:
            db.add(Phrase(
                phrase=entry.phrase,
                frequency_rank=entry.frequency_rank,
                frequency_count=entry.frequency_count,
            ))
            created += 1
    await db.commit()
    return {"status": "ok", "created": created, "updated": updated}
