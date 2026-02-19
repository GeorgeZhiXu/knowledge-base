from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.api.routes import curriculum, characters, import_data
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "knowledge-base"}
