"""CRUD routes for curriculum lessons."""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import Lesson

router = APIRouter()


class LessonCreate(BaseModel):
    grade: int
    volume: int
    unit_number: int = 0
    unit_title: Optional[str] = None
    lesson_number: int = 0
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


@router.get("/lessons")
async def list_lessons(grade: int | None = None, volume: int | None = None,
                       db: AsyncSession = Depends(get_session)):
    stmt = select(Lesson).order_by(Lesson.grade, Lesson.volume, Lesson.unit_number, Lesson.lesson_number)
    if grade is not None:
        stmt = stmt.where(Lesson.grade == grade)
    if volume is not None:
        stmt = stmt.where(Lesson.volume == volume)
    result = await db.exec(stmt)
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


@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    await db.delete(lesson)
    await db.commit()
