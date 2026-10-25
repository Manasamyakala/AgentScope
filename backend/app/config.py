import os

# Postgres in docker-compose; SQLite fallback so tests/dev work with zero setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentscope.db")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
