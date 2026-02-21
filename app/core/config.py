import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./data/knowledge.db"
)
PORT = int(os.environ.get("PORT", 8020))

BEDROCK_BEARER_TOKEN = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-20250514-v1:0")
