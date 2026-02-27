"""Learner activity tracking — test results and progress."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.models import TestResult

router = APIRouter()


# --- Request schemas ---

class TestResultEntry(BaseModel):
    word: str
    skill: str  # "read" or "write"
    passed: bool

class TestBatchCreate(BaseModel):
    learner: str
    session_title: Optional[str] = None
    session_notes: Optional[str] = None
    results: list[TestResultEntry] = []


# --- Submit test results ---

@router.post("/test-results", status_code=201)
async def submit_test_results(data: TestBatchCreate, db: AsyncSession = Depends(get_session)):
    """Submit a batch of test results."""
    now = datetime.utcnow()
    for entry in data.results:
        tr = TestResult(
            learner=data.learner,
            word=entry.word,
            skill=entry.skill,
            passed=entry.passed,
            tested_at=now,
            session_title=data.session_title,
            session_notes=data.session_notes,
        )
        db.add(tr)
    await db.commit()
    return {"status": "ok", "learner": data.learner, "count": len(data.results)}


# --- Progress ---

@router.get("/learners/{learner}/progress")
async def get_progress(learner: str, db: AsyncSession = Depends(get_session)):
    """Overall mastery summary for a learner."""
    all_results = await db.exec(
        select(TestResult)
        .where(TestResult.learner == learner)
        .order_by(TestResult.tested_at.desc())
    )

    latest = {}  # (word, skill) → passed
    for r in all_results.all():
        key = (r.word, r.skill)
        if key not in latest:
            latest[key] = r.passed

    read_mastered = sum(1 for (w, sk), p in latest.items() if sk == "read" and p)
    read_total = sum(1 for (w, sk) in latest if sk == "read")
    write_mastered = sum(1 for (w, sk), p in latest.items() if sk == "write" and p)
    write_total = sum(1 for (w, sk) in latest if sk == "write")

    return {
        "learner": learner,
        "total_words_tested": len(set(w for w, sk in latest)),
        "read": {"mastered": read_mastered, "total": read_total},
        "write": {"mastered": write_mastered, "total": write_total},
    }

@router.get("/learners/{learner}/progress/words")
async def get_word_progress(
    learner: str,
    skill: Optional[str] = None,
    status: Optional[str] = None,  # "passed" or "failed"
    db: AsyncSession = Depends(get_session),
):
    """Per-word latest status for a learner."""
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

    words = list(latest.values())
    if status == "passed":
        words = [w for w in words if w["passed"]]
    elif status == "failed":
        words = [w for w in words if not w["passed"]]

    words.sort(key=lambda w: (w["word"], w["skill"]))
    return words

@router.get("/learners/{learner}/words/{word}/history")
async def get_word_history(
    learner: str,
    word: str,
    db: AsyncSession = Depends(get_session),
):
    """All test attempts for a specific word by a learner."""
    result = await db.exec(
        select(TestResult)
        .where(TestResult.learner == learner)
        .where(TestResult.word == word)
        .order_by(TestResult.tested_at.desc())
    )
    return [
        {
            "skill": r.skill,
            "passed": r.passed,
            "tested_at": r.tested_at.isoformat(),
            "session_title": r.session_title,
        }
        for r in result.all()
    ]
