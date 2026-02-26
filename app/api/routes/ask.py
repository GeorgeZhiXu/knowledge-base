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

lessons (id UUID PK, grade INT, volume INT, unit_number INT, unit_title TEXT, lesson_number INT, title TEXT, page_start INT, page_end INT)
  -- grade: 1-6. volume: 1=上册, 2=下册. e.g. grade=4, volume=1 = 四年级上册
  -- unit_title: e.g. '课文（一）', '识字', '汉语拼音（一）'
  -- Filter by textbook: WHERE grade=4 AND volume=1


characters (character TEXT(1) PK, pinyin TEXT, standard_level INT, cumulative_percent REAL)
  -- standard_level: 《通用规范汉字表》level — 1=常用(top 3500), 2=次常用(3501-6500), 3=rare(6501+)
  -- cumulative_percent: cumulative text coverage percentage. LOWER value = MORE common character.
  --   e.g. 的=4.65%, 一=7.06%, 是=8.97% ... 99%+ are very rare characters.
  --   IMPORTANT: many characters have NULL cumulative_percent. Always filter with "cumulative_percent IS NOT NULL" when querying by frequency.
  --   "Top N most common characters" = ORDER BY cumulative_percent ASC LIMIT N (lowest % = most common)

character_lessons (character TEXT(1) FK→characters, lesson_id UUID FK→lessons, requirement TEXT, sort_order INT)
  -- PK: (character, lesson_id, requirement). requirement: 'recognize' (认识) or 'write' (会写)

phrases (id UUID PK, phrase TEXT UNIQUE, pinyin TEXT, meaning TEXT, notes TEXT)

phrase_lessons (phrase_id UUID FK→phrases, lesson_id UUID FK→lessons, sort_order INT)
  -- PK: (phrase_id, lesson_id)

learners (id UUID PK, name TEXT UNIQUE, created_at DATETIME)
  -- e.g. name='Ada'

test_sessions (id UUID PK, learner_id UUID FK→learners, lesson_id UUID FK→lessons nullable, title TEXT, tested_at DATETIME, notes TEXT)
  -- a quiz/practice session for a learner

test_results (id UUID PK, session_id UUID FK→test_sessions, learner_id UUID FK→learners, character TEXT(1) FK→characters, skill TEXT, passed BOOL, tested_at DATETIME)
  -- skill: 'read' or 'write'. passed: 1=mastered, 0=needs practice
  -- To find a learner's failed characters: JOIN learners ON learners.id = test_results.learner_id WHERE learners.name = '...' AND passed = 0

Key relationships:
- characters ←→ character_lessons ←→ lessons (which characters in which lessons)
- To find phrases containing a character: WHERE INSTR(phrase, character) > 0
- phrases ←→ phrase_lessons ←→ lessons (which phrases in which lessons)
- learners ←→ test_results ←→ characters (learner test history per character)

To get all characters for a textbook: JOIN character_lessons ON lesson_id, filter lessons by grade AND volume.
To get characters up to a certain lesson: additionally filter by unit_number and lesson_number.

Common query patterns:

1. "Top N most common characters":
   SELECT character, pinyin, cumulative_percent FROM characters
   WHERE cumulative_percent IS NOT NULL ORDER BY cumulative_percent ASC LIMIT N

2. "Characters [learner] failed":
   SELECT DISTINCT c.character, c.pinyin FROM characters c
   JOIN test_results tr ON tr.character = c.character
   JOIN learners l ON l.id = tr.learner_id
   WHERE l.name = '...' AND tr.passed = 0

3. "Top N common characters that [learner] failed":
   -- IMPORTANT: use a subquery to define the top-N pool first, then filter by learner results.
   -- Do NOT just LIMIT the final output — that limits result rows, not the character pool.
   SELECT DISTINCT c.character, c.pinyin, c.cumulative_percent FROM characters c
   JOIN test_results tr ON tr.character = c.character
   JOIN learners l ON l.id = tr.learner_id
   WHERE l.name = '...' AND tr.passed = 0
     AND c.character IN (
       SELECT character FROM characters WHERE cumulative_percent IS NOT NULL
       ORDER BY cumulative_percent ASC LIMIT N
     )
   ORDER BY c.cumulative_percent ASC

Important:
- A character can have MULTIPLE test_results rows (tested many times). Always use DISTINCT or GROUP BY on character to avoid duplicates.
- "Top N characters" means define the pool of N characters via subquery first, then apply other filters. The final result may be fewer than N rows.
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
- Lessons contain grade/volume directly. No need for joins to get textbook info. Filter by grade AND volume.
- When filtering by frequency/commonness, ALWAYS add "cumulative_percent IS NOT NULL" to exclude characters without frequency data.
- Lower cumulative_percent = more common. "Top N" or "most common N" means ORDER BY cumulative_percent ASC LIMIT N.
- When the user mentions a learner by name (e.g. "Ada"), always JOIN learners table on name, never assume the ID.
- Use standard_level for broad filtering (1=常用, 2=次常用, 3=rare). Use cumulative_percent for precise ranking.
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
