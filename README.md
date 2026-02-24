# Knowledge Base

Curriculum knowledge base API for storing and querying lesson content, tracking learner progress, and AI-powered natural language queries. Focused on Chinese (人教版 PEP) with an extensible schema for other subjects.

## Architecture

- **Backend**: Python FastAPI + SQLModel + SQLite
- **Port**: 8020 (API), 8021 (Datasette viewer)
- **Gateway**: `/knowledgebase/` (API), `/datasette/` (DB viewer)
- **API docs**: `/knowledgebase/docs` (Swagger UI)
- **AI queries**: Claude on Bedrock via `/api/v1/ask`

## Development & Deployment

| Path | Purpose |
|------|---------|
| `~/knowledge-base/` | Dev workspace (git repo) |
| `~/prod/knowledge-base/` | Production deployment |

Push to `main` triggers GitHub Actions deploy via SSH.

### Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]" sqlmodel aiosqlite pydantic greenlet anthropic httpx
mkdir -p data
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8020
```

## Database Schema

### Curriculum Hierarchy (generic)

```
subjects → textbooks → units → lessons
```

**subjects**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | str | unique — `"chinese"`, `"math"` |
| name | str | `"语文"`, `"数学"` |

**textbooks**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| subject_id | UUID | FK → subjects |
| publisher | str | `"人教版"` |
| grade | int | 1–12 |
| volume | int | 1=上册, 2=下册 |
| name | str | `"一年级上册"` |

**units**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| textbook_id | UUID | FK → textbooks |
| unit_number | int | sequential |
| title | str | `"第一单元"` |

**lessons**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| unit_id | UUID | FK → units |
| lesson_number | int | sequential |
| title | str | `"天地人"` |
| page_start | int | optional |
| page_end | int | optional |

### Requirement Types

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | str | `"recognize"`, `"read"`, `"write"`, `"recite"` |
| label | str | `"认识"`, `"会读"`, `"会写"`, `"背诵"` |

Seeded automatically on startup.

### Chinese Characters & Phrases

**characters** (keyed by the character itself)

| Column | Type | Notes |
|--------|------|-------|
| character | str(1) | **PK** — e.g. `"人"` |
| pinyin | str | `"rén"` |
| standard_level | int | 《通用规范汉字表》: 1=常用(top 3500), 2=次常用(3501-6500), 3=rare(6501+) |
| cumulative_percent | float | cumulative text coverage % |

**character_lessons** (which characters appear in which lessons)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| character | str(1) | FK → characters |
| lesson_id | UUID | FK → lessons |
| requirement_id | UUID | FK → requirement_types |
| sort_order | int | display order in lesson |

**phrases**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| phrase | str | unique — `"人民"` |
| pinyin | str | `"rén mín"` |
| meaning | str | optional |

**phrase_characters** (links phrases to constituent characters)

| Column | Type | Notes |
|--------|------|-------|
| phrase_id | UUID | FK → phrases |
| character | str(1) | FK → characters |
| position | int | 0-indexed position |

**phrase_lessons** (which phrases appear in which lessons)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| phrase_id | UUID | FK → phrases |
| lesson_id | UUID | FK → lessons |
| sort_order | int | display order in lesson |

### Learner Activity Tracking

**learners**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | str | unique |
| created_at | datetime | |

**test_sessions** (a quiz/practice session)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| learner_id | UUID | FK → learners |
| lesson_id | UUID | FK → lessons, optional |
| title | str | optional |
| tested_at | datetime | |
| notes | str | optional |

**test_results** (per-character result)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| session_id | UUID | FK → test_sessions |
| learner_id | UUID | FK → learners |
| character | str(1) | FK → characters |
| skill | str | `"read"` or `"write"` |
| passed | bool | true=mastered, false=needs practice |
| tested_at | datetime | |

### ER Diagram

```
subjects ─1:N─ textbooks ─1:N─ units ─1:N─ lessons
                                              │
                            ┌─────────────────┼─────────────────┐
                            │                 │                 │
                     character_lessons   phrase_lessons    test_sessions
                            │                 │                 │
                       characters          phrases          test_results
                            │                 │                 │
                            └── phrase_characters ──┘       learners
```

## API Endpoints

### Curriculum CRUD

```
GET/POST/DELETE  /api/v1/subjects
GET/POST         /api/v1/textbooks
DELETE           /api/v1/textbooks/{id}
GET              /api/v1/textbooks/{id}/units
POST/DELETE      /api/v1/units
GET              /api/v1/units/{id}/lessons
POST             /api/v1/lessons
GET/DELETE       /api/v1/lessons/{id}
```

### Characters & Phrases

```
GET/POST         /api/v1/characters
GET/DELETE       /api/v1/characters/{char}         — details + lessons + phrases
GET              /api/v1/characters/{char}/phrases
GET/POST         /api/v1/phrases
DELETE           /api/v1/phrases/{id}
GET              /api/v1/requirement-types
```

### Lesson Content

```
GET/POST  /api/v1/lessons/{id}/characters
GET/POST  /api/v1/lessons/{id}/phrases
```

### Cumulative Queries

```
GET  /api/v1/textbooks/{id}/characters?up_to_lesson=N
GET  /api/v1/textbooks/{id}/phrases?up_to_lesson=N
```

### Learner Activity

```
GET/POST         /api/v1/learners
GET/PUT/DELETE   /api/v1/learners/{id}
POST             /api/v1/test-sessions
DELETE           /api/v1/test-sessions/{id}
GET              /api/v1/learners/{id}/sessions
GET              /api/v1/learners/{id}/progress
GET              /api/v1/learners/{id}/progress/characters?skill=read&status=failed
GET              /api/v1/learners/{id}/characters/{char}/history
```

#### Submit test session:
```json
POST /api/v1/test-sessions
{
  "learner_id": "uuid",
  "title": "一年级上册 第1课",
  "results": [
    {"character": "天", "skill": "read", "passed": true},
    {"character": "天", "skill": "write", "passed": false}
  ]
}
```

#### Progress response:
```json
GET /api/v1/learners/{id}/progress
{
  "total_characters_tested": 3,
  "total_sessions": 1,
  "read": {"mastered": 3, "total": 3},
  "write": {"mastered": 2, "total": 3}
}
```

### AI Natural Language Query

```
POST /api/v1/ask
{"question": "一年级上册所有会写的字"}
→ {
    "sql": "SELECT ... FROM ...",
    "results": [...],
    "row_count": 42
  }
```

Powered by Claude on Bedrock. Converts natural language to SQL, executes read-only queries.

### Bulk Import

```
POST /api/v1/import/textbook   — entire textbook with units/lessons/characters/phrases
POST /api/v1/import/lesson     — characters + phrases for an existing lesson
POST /api/v1/import/frequency  — character frequency rankings
```

## Data

The SQLite database is committed to git (`data/knowledge.db`) for portability.

Current content:
- 12 textbooks (人教版 grades 1–6, 上册+下册)
- ~300 lessons, ~1,500 phrases
- ~12,800 characters with corpus frequency data (Jun Da/MTSU)
- Frequency coverage: top 100→39%, top 1000→86%, top 3500→99%

## Additional Services

- **Datasette**: Read-only web UI at `/datasette/` (port 8021) for browsing tables and running SQL
# Deployment test - 20260224_001733
