"""Natural language to SQL endpoint powered by Claude on Bedrock."""

import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_session
from app.core.config import BEDROCK_BEARER_TOKEN, BEDROCK_MODEL

router = APIRouter()

DB_SCHEMA = """
Tables in the knowledge base SQLite database:

subjects (id UUID PK, code TEXT UNIQUE, name TEXT, created_at DATETIME)
  -- e.g. code='chinese', name='语文'

textbooks (id UUID PK, subject_id UUID FK→subjects, publisher TEXT, grade INT, volume INT, name TEXT, created_at DATETIME)
  -- e.g. publisher='人教版', grade=1, volume=1 (上册), volume=2 (下册), name='一年级上册'

units (id UUID PK, textbook_id UUID FK→textbooks, unit_number INT, title TEXT)

lessons (id UUID PK, unit_id UUID FK→units, lesson_number INT, title TEXT, page_start INT, page_end INT)

requirement_types (id UUID PK, code TEXT UNIQUE, label TEXT)
  -- codes: 'recognize' (认识), 'read' (会读), 'write' (会写), 'recite' (背诵)

characters (character TEXT(1) PK, pinyin TEXT, stroke_count INT, radical TEXT, structure TEXT, frequency_rank INT, frequency_level INT, frequency_count INT, cumulative_percent REAL, notes TEXT)
  -- frequency_rank: corpus-based rank (1=的, 2=一, 3=不, ..., up to ~12000)
  -- frequency_level: 1=常用(top 3500), 2=次常用(3501-6500), 3=rare(6501+)
  -- frequency_count: raw occurrence count in corpus
  -- cumulative_percent: cumulative text coverage up to this rank

character_lessons (id UUID PK, character TEXT(1) FK→characters, lesson_id UUID FK→lessons, requirement_id UUID FK→requirement_types, sort_order INT)
  -- links characters to lessons with requirement type

phrases (id UUID PK, phrase TEXT UNIQUE, pinyin TEXT, meaning TEXT, notes TEXT)

phrase_characters (phrase_id UUID FK→phrases, character TEXT(1) FK→characters, position INT)
  -- links phrases to their constituent characters

phrase_lessons (id UUID PK, phrase_id UUID FK→phrases, lesson_id UUID FK→lessons, sort_order INT)

learners (id UUID PK, name TEXT, created_at DATETIME)

test_sessions (id UUID PK, learner_id UUID FK→learners, lesson_id UUID FK→lessons nullable, title TEXT, tested_at DATETIME, notes TEXT)
  -- a quiz/practice session for a learner

test_results (id UUID PK, session_id UUID FK→test_sessions, learner_id UUID FK→learners, character TEXT(1) FK→characters, skill TEXT, passed BOOL, tested_at DATETIME)
  -- skill: 'read' or 'write'. passed: true=mastered, false=needs practice

Key relationships:
- subjects → textbooks → units → lessons (curriculum hierarchy)
- characters ←→ character_lessons ←→ lessons (which characters in which lessons)
- characters ←→ phrase_characters ←→ phrases (which characters in which phrases)
- phrases ←→ phrase_lessons ←→ lessons (which phrases in which lessons)

Grade range: 1-6. Volume: 1=上册, 2=下册. Publisher: 人教版.
To get all characters up to a certain point, join through units and textbooks and filter by grade/volume/lesson_number.
"""

SYSTEM_PROMPT = f"""You are a SQL query generator for a Chinese language education knowledge base.
Given a natural language question, generate a single SQLite SELECT query to answer it.

{DB_SCHEMA}

Rules:
- Generate ONLY a single SELECT statement. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or any other modifying statement.
- Use SQLite syntax.
- LIMIT results to 200 rows max.
- Return ONLY the SQL query, no explanation, no markdown, no code fences. Just the raw SQL.
- For Chinese character lookups, the character column is the primary key (single character like '人').
- When joining through the curriculum hierarchy, remember: textbooks → units → lessons.
- Use frequency_rank for ordering by commonness (lower = more common).
"""

UNSAFE_PATTERN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|GRANT|REVOKE)\b',
    re.IGNORECASE,
)


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    sql: str
    results: list
    row_count: int


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest, db: AsyncSession = Depends(get_session)):
    """Ask a natural language question about the knowledge base. Returns SQL query and results."""
    if not BEDROCK_BEARER_TOKEN:
        raise HTTPException(status_code=503, detail="Bedrock API not configured")

    # Call Claude on Bedrock via bearer token auth
    try:
        import httpx as _httpx

        bedrock_url = f"https://bedrock-runtime.us-west-2.amazonaws.com/model/{BEDROCK_MODEL}/invoke"
        resp = _httpx.post(
            bedrock_url,
            headers={
                "Authorization": f"Bearer {BEDROCK_BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": req.question}],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise Exception(f"Bedrock returned {resp.status_code}: {resp.text[:200]}")
        message = resp.json()
        sql = message["content"][0]["text"].strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    # Strip markdown code fences if present
    if sql.startswith("```"):
        sql = re.sub(r'^```\w*\n?', '', sql)
        sql = re.sub(r'\n?```$', '', sql)
        sql = sql.strip()

    # Safety check
    if UNSAFE_PATTERN.search(sql):
        raise HTTPException(status_code=400, detail=f"Unsafe query rejected: {sql}")

    if not sql.upper().lstrip().startswith("SELECT"):
        raise HTTPException(status_code=400, detail=f"Only SELECT queries allowed. Got: {sql}")

    # Execute the query
    try:
        result = await db.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

        # Enforce limit
        if len(rows) > 200:
            rows = rows[:200]

        return AskResponse(
            question=req.question,
            sql=sql,
            results=rows,
            row_count=len(rows),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query execution error: {str(e)}\nSQL: {sql}")
