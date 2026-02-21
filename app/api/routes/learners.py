"""Learner activity tracking — test sessions, results, and progress."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.core.database import get_session
from app.models.models import Learner, TestSession, TestResult

router = APIRouter()


# --- Request schemas ---

class LearnerCreate(BaseModel):
    name: str

class TestResultEntry(BaseModel):
    character: str
    skill: str  # "read" or "write"
    passed: bool

class TestSessionCreate(BaseModel):
    learner_id: UUID
    lesson_id: Optional[UUID] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    results: list[TestResultEntry] = []


# --- Learners ---

@router.get("/learners")
async def list_learners(db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Learner).order_by(Learner.name))
    return result.all()

@router.post("/learners", status_code=201)
async def create_learner(data: LearnerCreate, db: AsyncSession = Depends(get_session)):
    learner = Learner(name=data.name)
    db.add(learner)
    await db.commit()
    await db.refresh(learner)
    return learner

@router.get("/learners/{learner_id}")
async def get_learner(learner_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(select(Learner).where(Learner.id == learner_id))
    learner = result.one_or_none()
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")
    return learner


# --- Test sessions ---

@router.post("/test-sessions", status_code=201)
async def create_test_session(data: TestSessionCreate, db: AsyncSession = Depends(get_session)):
    """Create a test session with batch results."""
    # Verify learner exists
    result = await db.exec(select(Learner).where(Learner.id == data.learner_id))
    if not result.one_or_none():
        raise HTTPException(status_code=404, detail="Learner not found")

    now = datetime.utcnow()
    session = TestSession(
        learner_id=data.learner_id,
        lesson_id=data.lesson_id,
        title=data.title,
        notes=data.notes,
        tested_at=now,
    )
    db.add(session)
    await db.flush()

    for entry in data.results:
        tr = TestResult(
            session_id=session.id,
            learner_id=data.learner_id,
            character=entry.character,
            skill=entry.skill,
            passed=entry.passed,
            tested_at=now,
        )
        db.add(tr)

    await db.commit()
    await db.refresh(session)
    return {
        "session_id": str(session.id),
        "learner_id": str(session.learner_id),
        "title": session.title,
        "tested_at": session.tested_at.isoformat(),
        "results_count": len(data.results),
    }

@router.get("/learners/{learner_id}/sessions")
async def list_sessions(learner_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.exec(
        select(TestSession)
        .where(TestSession.learner_id == learner_id)
        .order_by(TestSession.tested_at.desc())
    )
    sessions = result.all()
    output = []
    for s in sessions:
        count_result = await db.exec(
            select(func.count(TestResult.id)).where(TestResult.session_id == s.id)
        )
        count = count_result.one()
        passed_result = await db.exec(
            select(func.count(TestResult.id))
            .where(TestResult.session_id == s.id)
            .where(TestResult.passed == True)
        )
        passed = passed_result.one()
        output.append({
            "id": str(s.id),
            "title": s.title,
            "tested_at": s.tested_at.isoformat(),
            "total": count,
            "passed": passed,
            "notes": s.notes,
        })
    return output


# --- Progress ---

@router.get("/learners/{learner_id}/progress")
async def get_progress(learner_id: UUID, db: AsyncSession = Depends(get_session)):
    """Overall mastery summary for a learner."""
    # Total unique characters tested
    total_result = await db.exec(
        select(func.count(func.distinct(TestResult.character)))
        .where(TestResult.learner_id == learner_id)
    )
    total_tested = total_result.one()

    # Characters where latest read result is passed
    # Use a subquery to get latest result per character+skill
    for skill in ["read", "write"]:
        pass  # We'll compute below

    # Get all results, group by character+skill, take latest
    all_results = await db.exec(
        select(TestResult)
        .where(TestResult.learner_id == learner_id)
        .order_by(TestResult.tested_at.desc())
    )
    results = all_results.all()

    # Compute latest status per character+skill
    latest = {}  # (character, skill) → passed
    for r in results:
        key = (r.character, r.skill)
        if key not in latest:
            latest[key] = r.passed

    read_mastered = sum(1 for (ch, sk), p in latest.items() if sk == "read" and p)
    read_total = sum(1 for (ch, sk) in latest if sk == "read")
    write_mastered = sum(1 for (ch, sk), p in latest.items() if sk == "write" and p)
    write_total = sum(1 for (ch, sk) in latest if sk == "write")

    # Total sessions
    session_result = await db.exec(
        select(func.count(TestSession.id)).where(TestSession.learner_id == learner_id)
    )
    total_sessions = session_result.one()

    return {
        "learner_id": str(learner_id),
        "total_characters_tested": total_tested,
        "total_sessions": total_sessions,
        "read": {"mastered": read_mastered, "total": read_total},
        "write": {"mastered": write_mastered, "total": write_total},
    }

@router.get("/learners/{learner_id}/progress/characters")
async def get_character_progress(
    learner_id: UUID,
    skill: Optional[str] = None,
    status: Optional[str] = None,  # "passed" or "failed"
    db: AsyncSession = Depends(get_session),
):
    """Per-character latest status for a learner."""
    stmt = (
        select(TestResult)
        .where(TestResult.learner_id == learner_id)
        .order_by(TestResult.tested_at.desc())
    )
    if skill:
        stmt = stmt.where(TestResult.skill == skill)
    result = await db.exec(stmt)
    all_results = result.all()

    # Latest result per character+skill
    latest = {}
    for r in all_results:
        key = (r.character, r.skill)
        if key not in latest:
            latest[key] = {
                "character": r.character,
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

@router.get("/learners/{learner_id}/characters/{char}/history")
async def get_character_history(
    learner_id: UUID,
    char: str,
    db: AsyncSession = Depends(get_session),
):
    """All test attempts for a specific character by a learner."""
    result = await db.exec(
        select(TestResult)
        .where(TestResult.learner_id == learner_id)
        .where(TestResult.character == char)
        .order_by(TestResult.tested_at.desc())
    )
    return [
        {
            "skill": r.skill,
            "passed": r.passed,
            "tested_at": r.tested_at.isoformat(),
            "session_id": str(r.session_id),
        }
        for r in result.all()
    ]
