"""Routes for words (characters + phrases), lesson content, and cumulative queries."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from app.core.database import get_session
from app.models.models import Word, WordLesson, REQUIREMENT_LABELS, Lesson

router = APIRouter()


# --- Words (characters + phrases) ---

@router.get("/words")
async def list_words(q: str | None = None, db: AsyncSession = Depends(get_session)):
    stmt = select(Word).order_by(Word.word)
    if q:
        stmt = stmt.where(col(Word.word).contains(q))
    result = await db.exec(stmt)
    return result.all()


@router.post("/words", status_code=201)
async def create_word(data: dict, db: AsyncSession = Depends(get_session)):
    word = Word(**data)
    db.add(word)
    await db.commit()
    await db.refresh(word)
    return word


@router.get("/words/{word}")
async def get_word(word: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Word).where(Word.word == word))
    w = result.one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")

    # Get all lessons this word appears in
    wl_result = await db.exec(
        select(WordLesson, Lesson)
        .join(Lesson, WordLesson.lesson_id == Lesson.id)
        .where(WordLesson.word == word)
        .order_by(Lesson.grade, Lesson.volume, WordLesson.sort_order)
    )
    lessons = [
        {"lesson_id": wl.lesson_id, "lesson_title": l.title,
         "grade": l.grade, "volume": l.volume,
         "requirement": wl.requirement,
         "requirement_label": REQUIREMENT_LABELS.get(wl.requirement, wl.requirement)}
        for wl, l in wl_result.all()
    ]

    # For single characters, find phrases containing it
    phrases = []
    if len(word) == 1:
        phrase_result = await db.exec(
            select(Word).where(col(Word.word).contains(word))
            .where(Word.word != word)
            .order_by(func.length(Word.word), func.coalesce(Word.standard_level, 999))
            .limit(10)
        )
        phrases = [{"word": p.word, "pinyin": p.pinyin} for p in phrase_result.all()]

    return {**w.model_dump(), "lessons": lessons, "phrases": phrases}


# --- Lesson content ---

@router.get("/lessons/{lesson_id}/words")
async def get_lesson_words(lesson_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.exec(
        select(WordLesson, Word)
        .join(Word, WordLesson.word == Word.word)
        .where(WordLesson.lesson_id == lesson_id)
        .order_by(WordLesson.requirement, WordLesson.sort_order)
    )
    return [
        {**w.model_dump(), "requirement": wl.requirement,
         "requirement_label": REQUIREMENT_LABELS.get(wl.requirement, wl.requirement)}
        for wl, w in result.all()
    ]


@router.post("/lessons/{lesson_id}/words", status_code=201)
async def add_word_to_lesson(
    lesson_id: int, data: dict, db: AsyncSession = Depends(get_session)
):
    wl = WordLesson(
        word=data["word"],
        lesson_id=lesson_id,
        requirement=data["requirement"],
        sort_order=data.get("sort_order", 0),
    )
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return wl


# --- Cumulative queries ---

@router.get("/grades/{grade}/volumes/{volume}/words")
async def get_textbook_words(
    grade: int,
    volume: int,
    requirement: str | None = None,
    up_to_lesson: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Get all words in a textbook, optionally filtered by requirement and up to a lesson."""
    stmt = (
        select(Word, WordLesson, Lesson)
        .join(WordLesson, Word.word == WordLesson.word)
        .join(Lesson, WordLesson.lesson_id == Lesson.id)
        .where(Lesson.grade == grade, Lesson.volume == volume)
        .order_by(Lesson.unit_number, Lesson.lesson_number, WordLesson.sort_order)
    )
    if requirement:
        stmt = stmt.where(WordLesson.requirement == requirement)
    if up_to_lesson is not None:
        stmt = stmt.where(
            (Lesson.unit_number * 100 + Lesson.lesson_number) <= up_to_lesson
        )
    result = await db.exec(stmt)
    seen = set()
    words = []
    for w, wl, l in result.all():
        key = w.word
        words.append({
            **w.model_dump(),
            "requirement": wl.requirement,
            "requirement_label": REQUIREMENT_LABELS.get(wl.requirement, wl.requirement),
            "lesson_title": l.title,
            "unit_title": l.unit_title,
            "unit_number": l.unit_number,
            "lesson_number": l.lesson_number,
            "first_appearance": key not in seen,
        })
        seen.add(key)
    return words


# --- Deletes ---

@router.delete("/words/{word}", status_code=204)
async def delete_word(word: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Word).where(Word.word == word))
    w = result.one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")
    rows = await db.exec(select(WordLesson).where(WordLesson.word == word))
    for r in rows.all():
        await db.delete(r)
    await db.delete(w)
    await db.commit()
