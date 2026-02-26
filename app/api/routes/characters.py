"""Routes for characters, phrases, lesson content, and cumulative queries."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from app.core.database import get_session
from app.models.models import (
    Character, CharacterLesson, REQUIREMENT_LABELS,
    Phrase, PhraseLesson, Lesson,
)

router = APIRouter()


# --- Characters ---

@router.get("/characters")
async def list_characters(db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Character).order_by(Character.character))
    return result.all()


@router.post("/characters", status_code=201)
async def create_character(data: dict, db: AsyncSession = Depends(get_session)):
    char = Character(**data)
    db.add(char)
    await db.commit()
    await db.refresh(char)
    return char


@router.get("/characters/{char}")
async def get_character(char: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Character).where(Character.character == char))
    character = result.one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Get all lessons this character appears in
    cl_result = await db.exec(
        select(CharacterLesson, Lesson)
        .join(Lesson, CharacterLesson.lesson_id == Lesson.id)
        .where(CharacterLesson.character == char)
        .order_by(CharacterLesson.sort_order)
    )
    lessons = [
        {"lesson_id": str(cl.lesson_id), "lesson_title": l.title,
         "requirement": cl.requirement,
         "requirement_label": REQUIREMENT_LABELS.get(cl.requirement, cl.requirement)}
        for cl, l in cl_result.all()
    ]

    # Get phrases containing this character (derived from phrase text)
    phrase_result = await db.exec(
        select(Phrase).where(col(Phrase.phrase).contains(char)).order_by(Phrase.phrase)
    )
    phrases = [{"phrase": p.phrase, "pinyin": p.pinyin}
               for p in phrase_result.all()]

    return {
        **character.model_dump(),
        "lessons": lessons,
        "phrases": phrases,
    }


# --- Phrases ---

@router.get("/phrases")
async def list_phrases(db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Phrase).order_by(Phrase.phrase))
    return result.all()


@router.post("/phrases", status_code=201)
async def create_phrase(data: dict, db: AsyncSession = Depends(get_session)):
    phrase = Phrase(
        phrase=data["phrase"],
        pinyin=data.get("pinyin", ""),
        meaning=data.get("meaning"),
        notes=data.get("notes"),
    )
    db.add(phrase)
    await db.commit()
    await db.refresh(phrase)
    return phrase


# --- Lesson content ---

@router.get("/lessons/{lesson_id}/characters")
async def get_lesson_characters(lesson_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(
        select(CharacterLesson, Character)
        .join(Character, CharacterLesson.character == Character.character)
        .where(CharacterLesson.lesson_id == lesson_id)
        .order_by(CharacterLesson.sort_order)
    )
    return [
        {**c.model_dump(), "requirement": cl.requirement,
         "requirement_label": REQUIREMENT_LABELS.get(cl.requirement, cl.requirement)}
        for cl, c in result.all()
    ]


@router.post("/lessons/{lesson_id}/characters", status_code=201)
async def add_character_to_lesson(
    lesson_id: UUID, data: dict, db: AsyncSession = Depends(get_session)
):
    cl = CharacterLesson(
        character=data["character"],
        lesson_id=lesson_id,
        requirement=data["requirement"],
        sort_order=data.get("sort_order", 0),
    )
    db.add(cl)
    await db.commit()
    await db.refresh(cl)
    return cl


@router.get("/lessons/{lesson_id}/phrases")
async def get_lesson_phrases(lesson_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(
        select(Phrase)
        .join(PhraseLesson, Phrase.phrase == PhraseLesson.phrase)
        .where(PhraseLesson.lesson_id == lesson_id)
        .order_by(PhraseLesson.sort_order)
    )
    return result.all()


@router.post("/lessons/{lesson_id}/phrases", status_code=201)
async def add_phrase_to_lesson(
    lesson_id: UUID, data: dict, db: AsyncSession = Depends(get_session)
):
    pl = PhraseLesson(
        phrase=data["phrase"],
        lesson_id=lesson_id,
        sort_order=data.get("sort_order", 0),
    )
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return pl


# --- Cumulative queries ---

@router.get("/grades/{grade}/volumes/{volume}/characters")
async def get_textbook_characters(
    grade: int,
    volume: int,
    up_to_lesson: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Get all characters in a textbook, optionally up to a lesson number."""
    stmt = (
        select(Character, CharacterLesson, Lesson)
        .join(CharacterLesson, Character.character == CharacterLesson.character)
        .join(Lesson, CharacterLesson.lesson_id == Lesson.id)
        .where(Lesson.grade == grade, Lesson.volume == volume)
        .order_by(Lesson.unit_number, Lesson.lesson_number, CharacterLesson.sort_order)
    )
    if up_to_lesson is not None:
        stmt = stmt.where(
            (Lesson.unit_number * 100 + Lesson.lesson_number) <= up_to_lesson
        )
    result = await db.exec(stmt)
    seen = set()
    characters = []
    for c, cl, l in result.all():
        key = c.character
        characters.append({
            **c.model_dump(),
            "requirement": cl.requirement,
            "requirement_label": REQUIREMENT_LABELS.get(cl.requirement, cl.requirement),
            "lesson_title": l.title,
            "unit_title": l.unit_title,
            "unit_number": l.unit_number,
            "lesson_number": l.lesson_number,
            "first_appearance": key not in seen,
        })
        seen.add(key)
    return characters


@router.get("/grades/{grade}/volumes/{volume}/phrases")
async def get_textbook_phrases(
    grade: int,
    volume: int,
    up_to_lesson: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Get all phrases in a textbook, optionally up to a lesson number."""
    stmt = (
        select(Phrase, PhraseLesson, Lesson)
        .join(PhraseLesson, Phrase.phrase == PhraseLesson.phrase)
        .join(Lesson, PhraseLesson.lesson_id == Lesson.id)
        .where(Lesson.grade == grade, Lesson.volume == volume)
        .order_by(Lesson.unit_number, Lesson.lesson_number, PhraseLesson.sort_order)
    )
    if up_to_lesson is not None:
        stmt = stmt.where(
            (Lesson.unit_number * 100 + Lesson.lesson_number) <= up_to_lesson
        )
    result = await db.exec(stmt)
    return [
        {**p.model_dump(), "lesson_title": l.title, "unit_title": l.unit_title}
        for p, pl, l in result.all()
    ]


# --- Deletes ---

@router.delete("/characters/{char}", status_code=204)
async def delete_character(char: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Character).where(Character.character == char))
    character = result.one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    rows = await db.exec(select(CharacterLesson).where(CharacterLesson.character == char))
    for r in rows.all():
        await db.delete(r)
    await db.delete(character)
    await db.commit()

@router.delete("/phrases/{phrase_text}", status_code=204)
async def delete_phrase(phrase_text: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Phrase).where(Phrase.phrase == phrase_text))
    phrase = result.one_or_none()
    if not phrase:
        raise HTTPException(status_code=404, detail="Phrase not found")
    pls = await db.exec(select(PhraseLesson).where(PhraseLesson.phrase == phrase_text))
    for r in pls.all():
        await db.delete(r)
    await db.delete(phrase)
    await db.commit()
