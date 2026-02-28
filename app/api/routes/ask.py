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

lessons (id INTEGER PK AUTO, grade INT, volume INT, unit_number INT, unit_title TEXT, lesson_number INT, title TEXT, page_start INT, page_end INT)
  -- grade: 1-6. volume: 1=上册, 2=下册. e.g. grade=4, volume=1 = 四年级上册
  -- unit_title: e.g. '课文（一）', '识字', '汉语拼音（一）'
  -- Filter by textbook: WHERE grade=4 AND volume=1


words (word TEXT PK, pinyin TEXT, meaning TEXT, standard_level INT, cumulative_percent REAL, radical TEXT, decomposition TEXT, etymology_type TEXT, phonetic TEXT, semantic TEXT)
  -- Unified table for both single characters (e.g. '人') and phrases (e.g. '人民')
  -- Single characters: length(word) = 1. Phrases: length(word) > 1.
  -- standard_level: 《通用规范汉字表》level — 1=常用(top 3500), 2=次常用(3501-6500), 3=rare(6501+)
  -- cumulative_percent: cumulative text coverage. LOWER = MORE common.
  --   IMPORTANT: many words have NULL cumulative_percent. Always filter with "cumulative_percent IS NOT NULL" when querying by frequency.
  --   "Top N most common" = ORDER BY cumulative_percent ASC LIMIT N
  -- radical: the character's radical (部首), e.g. '氵' for 河. Only for single characters.
  -- decomposition: IDS decomposition, e.g. '⿰氵可' for 河. ⿰=left-right, ⿱=top-bottom, ⿴=surround, etc.
  -- etymology_type: 'pictographic' (象形), 'ideographic' (会意), 'pictophonetic' (形声)
  -- phonetic: the phonetic component for pictophonetic characters, e.g. '可' for 河
  -- semantic: the semantic component, e.g. '氵' for 河
  -- To find characters with same radical: WHERE radical = '氵' AND length(word) = 1
  -- To find characters with same phonetic: WHERE phonetic = '青' AND length(word) = 1

word_lessons (word TEXT FK→words, lesson_id INT FK→lessons, requirement TEXT, sort_order INT)
  -- PK: (word, lesson_id, requirement). requirement: 'recognize' (认识) or 'write' (会写)

test_results (id INTEGER PK AUTO, learner TEXT, word TEXT FK→words, skill TEXT, passed BOOL, tested_at DATETIME, session_title TEXT, session_notes TEXT)
  -- learner: username string (e.g. 'Ada'). skill: 'read' or 'write'. passed: 1=mastered, 0=needs practice
  -- To find a learner's failed words: WHERE learner = 'Ada' AND passed = 0

Key relationships:
- words ←→ word_lessons ←→ lessons (which words in which lessons)
- To find phrases containing a character: WHERE INSTR(word, '人') > 0 AND length(word) > 1
- test_results links learner (by username) to words with pass/fail history

To get all words for a textbook: JOIN word_lessons ON lesson_id, filter lessons by grade AND volume.
To get single characters only: add WHERE length(w.word) = 1.
To get phrases only: add WHERE length(w.word) > 1.

Common query patterns:

1. "Top N most common characters":
   SELECT word, pinyin, cumulative_percent FROM words
   WHERE length(word) = 1 AND cumulative_percent IS NOT NULL ORDER BY cumulative_percent ASC LIMIT N

2. "Words [learner] failed":
   SELECT DISTINCT w.word, w.pinyin FROM words w
   JOIN test_results tr ON tr.word = w.word
   WHERE tr.learner = '...' AND tr.passed = 0

3. "Top N common characters that [learner] failed":
   SELECT DISTINCT w.word, w.pinyin, w.cumulative_percent FROM words w
   JOIN test_results tr ON tr.word = w.word
   WHERE tr.learner = '...' AND tr.passed = 0
     AND w.word IN (
       SELECT word FROM words WHERE length(word) = 1 AND cumulative_percent IS NOT NULL
       ORDER BY cumulative_percent ASC LIMIT N
     )
   ORDER BY w.cumulative_percent ASC

Important:
- A word can have MULTIPLE test_results rows (tested many times). Always use DISTINCT or GROUP BY on word to avoid duplicates.
- "Top N" means define the pool via subquery first, then apply other filters. The final result may be fewer than N rows.
"""

SYSTEM_PROMPT = f"""You are a SQL query generator for a Chinese language education knowledge base.
Given a natural language question, generate a single SQLite SELECT query to answer it.

{DB_SCHEMA}

Rules:
- Generate ONLY a single SELECT statement. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or any other modifying statement.
- Use SQLite syntax.
- LIMIT results to 200 rows max.
- Return ONLY the SQL query, no explanation, no markdown, no code fences. Just the raw SQL.
- The words table contains both single characters ('人') and phrases ('人民'). Use length(word)=1 for characters only, length(word)>1 for phrases only.
- Lessons contain grade/volume directly. No need for joins to get textbook info. Filter by grade AND volume.
- When filtering by frequency/commonness, ALWAYS add "cumulative_percent IS NOT NULL" to exclude characters without frequency data.
- Lower cumulative_percent = more common. "Top N" or "most common N" means ORDER BY cumulative_percent ASC LIMIT N.
- When the user mentions a learner by name (e.g. "Ada"), filter test_results directly: WHERE learner = 'Ada'. No JOIN needed.
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
