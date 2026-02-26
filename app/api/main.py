from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from app.core.database import init_db, engine
from app.api.routes import curriculum, characters, import_data, ask, learners
from app.models.models import RequirementType
from app.core.database import async_session
from sqlmodel import select


async def seed_requirement_types():
    """Seed default requirement types if they don't exist."""
    defaults = [
        ("recognize", "认识"),
        ("read", "会读"),
        ("write", "会写"),
        ("recite", "背诵"),
    ]
    async with async_session() as db:
        for code, label in defaults:
            result = await db.exec(
                select(RequirementType).where(RequirementType.code == code)
            )
            if not result.one_or_none():
                db.add(RequirementType(code=code, label=label))
        await db.commit()


async def migrate_db():
    """Run schema migrations for existing databases."""
    async with engine.begin() as conn:
        # --- Lessons table: flatten curriculum hierarchy ---
        result = await conn.execute(text("PRAGMA table_info(lessons)"))
        lesson_cols = {row[1] for row in result.fetchall()}

        if "unit_id" in lesson_cols and "grade" not in lesson_cols:
            # Old schema: flatten subjects/textbooks/units into lessons
            for col, coltype in [("grade", "INTEGER"), ("volume", "INTEGER"),
                                  ("unit_number", "INTEGER"), ("unit_title", "TEXT")]:
                await conn.execute(text(f"ALTER TABLE lessons ADD COLUMN {col} {coltype}"))
            await conn.execute(text("""
                UPDATE lessons SET
                  grade = (SELECT t.grade FROM units u JOIN textbooks t ON t.id = u.textbook_id WHERE u.id = lessons.unit_id),
                  volume = (SELECT t.volume FROM units u JOIN textbooks t ON t.id = u.textbook_id WHERE u.id = lessons.unit_id),
                  unit_number = (SELECT u.unit_number FROM units u WHERE u.id = lessons.unit_id),
                  unit_title = (SELECT u.title FROM units u WHERE u.id = lessons.unit_id)
            """))

        # --- Phrases table: add columns if missing ---
        for col, coltype in [
            ("frequency_rank", "INTEGER"),
            ("frequency_level", "INTEGER"),
            ("frequency_count", "INTEGER"),
            ("cumulative_percent", "REAL"),
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE phrases ADD COLUMN {col} {coltype}"))
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await migrate_db()
    await seed_requirement_types()
    yield


app = FastAPI(
    title="Knowledge Base API",
    description="Curriculum knowledge base for Chinese characters, phrases, and lesson tracking",
    version="0.1.0",
    lifespan=lifespan,
    root_path="/knowledgebase",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(curriculum.router, prefix="/api/v1", tags=["curriculum"])
app.include_router(characters.router, prefix="/api/v1", tags=["characters"])
app.include_router(import_data.router, prefix="/api/v1", tags=["import"])
app.include_router(ask.router, prefix="/api/v1", tags=["ask"])
app.include_router(learners.router, prefix="/api/v1", tags=["learners"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "knowledge-base"}
