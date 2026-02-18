"""Bulk import route for populating lesson data efficiently."""

from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import (
    Character, CharacterLesson, RequirementType,
    Phrase, PhraseCharacter, PhraseLesson,
)

router = APIRouter()


@router.post("/import/lesson")
async def import_lesson_data(data: dict, db: AsyncSession = Depends(get_session)):
    """Bulk import characters and phrases for a lesson.

    Expected payload:
    {
        "lesson_id": "uuid",
        "characters": [
            {"character": "天", "pinyin": "tiān", "requirement": "recognize"},
            {"character": "地", "pinyin": "dì", "requirement": "write"}
        ],
        "phrases": [
            {"phrase": "天地", "pinyin": "tiān dì"},
            {"phrase": "人民", "pinyin": "rén mín", "meaning": "people"}
        ]
    }
    """
    lesson_id = UUID(data["lesson_id"])
    stats = {"characters_created": 0, "character_lessons_created": 0,
             "phrases_created": 0, "phrase_lessons_created": 0}

    # Cache requirement types
    rt_result = await db.exec(select(RequirementType))
    req_map = {rt.code: rt.id for rt in rt_result.all()}

    # Import characters
    for i, ch_data in enumerate(data.get("characters", [])):
        char_str = ch_data["character"]
        # Create or get character
        existing = await db.exec(
            select(Character).where(Character.character == char_str)
        )
        if not existing.one_or_none():
            char = Character(
                character=char_str,
                pinyin=ch_data.get("pinyin", ""),
                stroke_count=ch_data.get("stroke_count"),
                radical=ch_data.get("radical"),
                structure=ch_data.get("structure"),
            )
            db.add(char)
            stats["characters_created"] += 1

        # Link to lesson
        req_code = ch_data.get("requirement", "recognize")
        req_id = req_map.get(req_code)
        if req_id:
            # Check if link already exists
            existing_cl = await db.exec(
                select(CharacterLesson)
                .where(CharacterLesson.character == char_str)
                .where(CharacterLesson.lesson_id == lesson_id)
                .where(CharacterLesson.requirement_id == req_id)
            )
            if not existing_cl.one_or_none():
                cl = CharacterLesson(
                    character=char_str,
                    lesson_id=lesson_id,
                    requirement_id=req_id,
                    sort_order=i,
                )
                db.add(cl)
                stats["character_lessons_created"] += 1

    # Import phrases
    for i, ph_data in enumerate(data.get("phrases", [])):
        phrase_str = ph_data["phrase"]
        # Create or get phrase
        existing = await db.exec(
            select(Phrase).where(Phrase.phrase == phrase_str)
        )
        phrase = existing.one_or_none()
        if not phrase:
            phrase = Phrase(
                phrase=phrase_str,
                pinyin=ph_data.get("pinyin", ""),
                meaning=ph_data.get("meaning"),
                notes=ph_data.get("notes"),
            )
            db.add(phrase)
            await db.flush()
            stats["phrases_created"] += 1

            # Auto-create phrase_characters
            for j, ch in enumerate(phrase_str):
                char_exists = await db.exec(
                    select(Character).where(Character.character == ch)
                )
                if char_exists.one_or_none():
                    pc = PhraseCharacter(
                        phrase_id=phrase.id, character=ch, position=j
                    )
                    db.add(pc)

        # Link phrase to lesson
        existing_pl = await db.exec(
            select(PhraseLesson)
            .where(PhraseLesson.phrase_id == phrase.id)
            .where(PhraseLesson.lesson_id == lesson_id)
        )
        if not existing_pl.one_or_none():
            pl = PhraseLesson(
                phrase_id=phrase.id,
                lesson_id=lesson_id,
                sort_order=i,
            )
            db.add(pl)
            stats["phrase_lessons_created"] += 1

    await db.commit()
    return {"status": "ok", **stats}
