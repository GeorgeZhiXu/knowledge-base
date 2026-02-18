# Knowledge Base

Curriculum knowledge base API for storing and querying lesson content. Focused on Chinese (人教版 PEP) with an extensible schema for other subjects.

## Architecture

- **Backend**: Python FastAPI + SQLModel + SQLite
- **Port**: 8020
- **Gateway**: `/knowledgebase/` (auth required)
- **API docs**: `/knowledgebase/docs` (Swagger UI)

## Development & Deployment

| Path | Purpose |
|------|---------|
| `~/knowledge-base/` | Dev workspace (git repo) |
| `~/prod/knowledge-base/` | Production deployment |

Push to `main` triggers GitHub Actions deploy via SSH.

### Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]" sqlmodel aiosqlite pydantic greenlet
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
| stroke_count | int | optional |
| radical | str | optional — `"亻"` |
| structure | str | optional — `"独体"`, `"左右"`, `"上下"` |

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

### ER Diagram

```
subjects ─1:N─ textbooks ─1:N─ units ─1:N─ lessons
                                              │
                            ┌─────────────────┼─────────────────┐
                            │                 │                 │
                     character_lessons   phrase_lessons          │
                            │                 │                 │
                       characters          phrases              │
                            │                 │                 │
                            └────── phrase_characters ──────────┘
```

## API Endpoints

### Curriculum CRUD

```
GET/POST  /api/v1/subjects
GET/POST  /api/v1/textbooks
GET       /api/v1/textbooks/{id}/units
POST      /api/v1/units
GET       /api/v1/units/{id}/lessons
POST      /api/v1/lessons
GET       /api/v1/lessons/{id}
```

### Characters & Phrases

```
GET/POST  /api/v1/characters
GET       /api/v1/characters/{char}           — details + lessons + phrases
GET       /api/v1/characters/{char}/phrases   — all phrases containing this character
GET/POST  /api/v1/phrases
GET       /api/v1/requirement-types
```

### Lesson Content

```
GET/POST  /api/v1/lessons/{id}/characters     — characters in a lesson
GET/POST  /api/v1/lessons/{id}/phrases        — phrases in a lesson
```

### Cumulative Queries

```
GET       /api/v1/textbooks/{id}/characters?up_to_lesson=N
GET       /api/v1/textbooks/{id}/phrases?up_to_lesson=N
```

### Bulk Import

```
POST      /api/v1/import/lesson
```

Payload:
```json
{
  "lesson_id": "uuid",
  "characters": [
    {"character": "天", "pinyin": "tiān", "requirement": "recognize"},
    {"character": "人", "pinyin": "rén", "requirement": "write"}
  ],
  "phrases": [
    {"phrase": "天地", "pinyin": "tiān dì"},
    {"phrase": "人民", "pinyin": "rén mín", "meaning": "people"}
  ]
}
```

## Example: 人教版一年级上册

```
Subject: 语文 (chinese)
Textbook: 人教版一年级上册 (grade=1, volume=1)
  Unit 1: 第一单元
    Lesson 1: 天地人
      Characters: 天(recognize), 地(recognize), 人(recognize)
      Phrases: 天地, 人民
    Lesson 2: 金木水火土
      Characters: 金(recognize), 木(recognize), 水(recognize), 火(recognize), 土(recognize)
```
