import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./data/knowledge.db"
)
PORT = int(os.environ.get("PORT", 8020))
