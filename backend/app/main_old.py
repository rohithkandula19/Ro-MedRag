"""
Healthcare Research Assistant - FastAPI Backend
Production-grade RAG system for medical literature analysis.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.database import create_db_and_tables
from app.api.routes import auth, documents, chat, admin, health

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("🚀 Healthcare RAG System starting up...")
    await create_db_and_tables()
    logger.info("✅ Database initialized")
    yield
    logger.info("🛑 Healthcare RAG System shutting down...")


app = FastAPI(
    title="Healthcare Research Assistant API",
    description="Production-grade RAG system for medical literature analysis",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
)

# ── Middleware ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)"
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


# ── Routers ─────────────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
