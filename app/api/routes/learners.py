"""Learner activity tracking — test sessions, results, and progress."""

from datetime import datetime
from typing import Optional


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.core.database import get_session
from app.models.models import TestSession, TestResult

router = APIRouter()


# --- Request schemas ---

class TestResultEntry(BaseModel):
    character: str
    skill: str  # "read" or "write"
    passed: bool

class TestSessionCreate(BaseModel):
    learner: str  # username
    lesson_id: Optional[int] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    results: list[TestResultEntry] = []


# --- Test sessions ---

@router.post("/test-sessions", status_code=201)
async def create_test_session(data: TestSessionCreate, db: AsyncSession = Depends(get_session)):
    """Create a test session with batch results."""
    now = datetime.utcnow()
    session = TestSession(
        learner=data.learner,
        lesson_id=data.lesson_id,
        title=data.title,
        notes=data.notes,
        tested_at=now,
    )
    db.add(session)
    await db.flush()

    for entry in data.results:
        tr = TestResult(
            learner=data.learner,
            session_id=session.id,
            word=entry.word,
            skill=entry.skill,
            passed=entry.passed,
            tested_at=now,
        )
        db.add(tr)

    await db.commit()
    await db.refresh(session)
    return {
        "session_id": str(session.id),
        "learner": session.learner,
        "title": session.title,
        "tested_at": session.tested_at.isoformat(),
        "results_count": len(data.results),
    }

@router.delete("/test-sessions/{session_id}", status_code=204)
async def delete_test_session(session_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(TestSession).where(TestSession.id == session_id))
    session = result.one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    results = await db.exec(select(TestResult).where(TestResult.session_id == session_id))
    for r in results.all():
        await db.delete(r)
    await db.delete(session)
    await db.commit()

@router.get("/learners/{learner}/sessions")
async def list_sessions(learner: str, db: AsyncSession = Depends(get_session)):
    result = await db.exec(
        select(TestSession)
        .where(TestSession.learner == learner)
        .order_by(TestSession.tested_at.desc())
    )
    return [
        {
            "id": str(s.id),
            "title": s.title,
            "tested_at": s.tested_at.isoformat(),
            "notes": s.notes,
        }
        for s in result.all()
    ]


# --- Progress ---

@router.get("/learners/{learner}/progress")
async def get_progress(learner: str, db: AsyncSession = Depends(get_session)):
    """Overall mastery summary for a learner."""
    all_results = await db.exec(
        select(TestResult)
        .where(TestResult.learner == learner)
        .order_by(TestResult.tested_at.desc())
    )

    latest = {}  # (character, skill) → passed
    for r in all_results.all():
        key = (r.word, r.skill)
        if key not in latest:
            latest[key] = r.passed

    read_mastered = sum(1 for (ch, sk), p in latest.items() if sk == "read" and p)
    read_total = sum(1 for (ch, sk) in latest if sk == "read")
    write_mastered = sum(1 for (ch, sk), p in latest.items() if sk == "write" and p)
    write_total = sum(1 for (ch, sk) in latest if sk == "write")

    session_result = await db.exec(
        select(func.count(TestSession.id)).where(TestSession.learner == learner)
    )

    return {
        "learner": learner,
        "total_characters_tested": len(set(ch for ch, sk in latest)),
        "total_sessions": session_result.one(),
        "read": {"mastered": read_mastered, "total": read_total},
        "write": {"mastered": write_mastered, "total": write_total},
    }

@router.get("/learners/{learner}/progress/characters")
async def get_character_progress(
    learner: str,
    skill: Optional[str] = None,
    status: Optional[str] = None,  # "passed" or "failed"
    db: AsyncSession = Depends(get_session),
):
    """Per-character latest status for a learner."""
    stmt = (
        select(TestResult)
        .where(TestResult.learner == learner)
        .order_by(TestResult.tested_at.desc())
    )
    if skill:
        stmt = stmt.where(TestResult.skill == skill)
    result = await db.exec(stmt)

    latest = {}
    for r in result.all():
        key = (r.word, r.skill)
        if key not in latest:
            latest[key] = {
                "word": r.word,
                "skill": r.skill,
                "passed": r.passed,
                "tested_at": r.tested_at.isoformat(),
            }

    chars = list(latest.values())
    if status == "passed":
        chars = [c for c in chars if c["passed"]]
    elif status == "failed":
        chars = [c for c in chars if not c["passed"]]

    chars.sort(key=lambda c: (c["character"], c["skill"]))
    return chars

@router.get("/learners/{learner}/words/{word}/history")
async def get_character_history(
    learner: str,
    word: str,
    db: AsyncSession = Depends(get_session),
):
    """All test attempts for a specific character by a learner."""
    result = await db.exec(
        select(TestResult)
        .where(TestResult.learner == learner)
        .where(TestResult.word == char)
        .order_by(TestResult.tested_at.desc())
    )
    return [
        {
            "skill": r.skill,
            "passed": r.passed,
            "tested_at": r.tested_at.isoformat(),
            "session_id": str(r.session_id) if r.session_id else None,
        }
        for r in result.all()
    ]
