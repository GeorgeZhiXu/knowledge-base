"""CRUD routes for curriculum hierarchy: subjects, textbooks, units, lessons."""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import Subject, Textbook, Unit, Lesson

router = APIRouter()


# --- Request schemas ---

class SubjectCreate(BaseModel):
    code: str
    name: str

class TextbookCreate(BaseModel):
    subject_id: UUID
    publisher: str
    grade: int
    volume: int
    name: str

class UnitCreate(BaseModel):
    textbook_id: UUID
    unit_number: int
    title: str

class LessonCreate(BaseModel):
    unit_id: UUID
    lesson_number: int
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


# --- Subjects ---

@router.get("/subjects")
async def list_subjects(db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Subject).order_by(Subject.name))
    return result.all()

@router.post("/subjects", status_code=201)
async def create_subject(data: SubjectCreate, db: AsyncSession = Depends(get_session)):
    subject = Subject(**data.model_dump())
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


# --- Textbooks ---

@router.get("/textbooks")
async def list_textbooks(subject_id: UUID | None = None, db: AsyncSession = Depends(get_session)):
    stmt = select(Textbook).order_by(Textbook.grade, Textbook.volume)
    if subject_id:
        stmt = stmt.where(Textbook.subject_id == subject_id)
    result = await db.exec(stmt)
    return result.all()

@router.post("/textbooks", status_code=201)
async def create_textbook(data: TextbookCreate, db: AsyncSession = Depends(get_session)):
    textbook = Textbook(**data.model_dump())
    db.add(textbook)
    await db.commit()
    await db.refresh(textbook)
    return textbook


# --- Units ---

@router.get("/textbooks/{textbook_id}/units")
async def list_units(textbook_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Unit).where(Unit.textbook_id == textbook_id).order_by(Unit.unit_number))
    return result.all()

@router.post("/units", status_code=201)
async def create_unit(data: UnitCreate, db: AsyncSession = Depends(get_session)):
    unit = Unit(**data.model_dump())
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return unit


# --- Lessons ---

@router.get("/units/{unit_id}/lessons")
async def list_lessons(unit_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Lesson).where(Lesson.unit_id == unit_id).order_by(Lesson.lesson_number))
    return result.all()

@router.post("/lessons", status_code=201)
async def create_lesson(data: LessonCreate, db: AsyncSession = Depends(get_session)):
    lesson = Lesson(**data.model_dump())
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return lesson

@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


# --- Deletes (cascade) ---

@router.delete("/subjects/{subject_id}", status_code=204)
async def delete_subject(subject_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Subject).where(Subject.id == subject_id))
    subject = result.one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    await db.delete(subject)
    await db.commit()

@router.delete("/textbooks/{textbook_id}", status_code=204)
async def delete_textbook(textbook_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Textbook).where(Textbook.id == textbook_id))
    textbook = result.one_or_none()
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
    await db.delete(textbook)
    await db.commit()

@router.delete("/units/{unit_id}", status_code=204)
async def delete_unit(unit_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Unit).where(Unit.id == unit_id))
    unit = result.one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    await db.delete(unit)
    await db.commit()

@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    await db.delete(lesson)
    await db.commit()
