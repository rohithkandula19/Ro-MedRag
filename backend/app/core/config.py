"""Application configuration — all settings from environment variables."""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import secrets


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "Healthcare Research Assistant"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/healthcare_rag"

    # ── AI / LLM ──────────────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "anthropic"          # "openai" | "anthropic"
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"
    EMBEDDING_MODEL: str = "text-embedding-3-small"  # OpenAI embeddings
    EMBEDDING_DIMENSION: int = 1536
    LLM_TEMPERATURE: float = 0.0             # 0 = factual, deterministic
    LLM_MAX_TOKENS: int = 2048

    # ── Vector DB ─────────────────────────────────────────────────────────
    VECTOR_DB: str = "faiss"                 # "faiss" | "pinecone"
    FAISS_INDEX_PATH: str = "./data/faiss_index"
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_INDEX_NAME: str = "healthcare-rag"

    # ── RAG Pipeline ──────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K_RETRIEVAL: int = 8
    TOP_K_RERANK: int = 4
    MIN_RELEVANCE_SCORE: float = 0.35
    MAX_CONTEXT_TOKENS: int = 6000

    # ── File Upload ───────────────────────────────────────────────────────
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [".pdf"]
    UPLOAD_DIR: str = "./data/uploads"

    # ── Auth / JWT ────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    CHAT_RATE_LIMIT: int = 20             # queries per minute per user

    # ── Redis (optional, for rate limiting + caching) ─────────────────────
    REDIS_URL: Optional[str] = None

    # ── GCP ───────────────────────────────────────────────────────────────
    GCP_PROJECT_ID: Optional[str] = None
    GCP_BUCKET_NAME: Optional[str] = None
    GCP_REGION: str = "us-central1"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
