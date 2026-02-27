from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.api.routes import curriculum, characters, import_data, ask, learners


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
