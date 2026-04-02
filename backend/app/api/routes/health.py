"""Health check route."""
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

@router.get("/")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "Healthcare Research Assistant API",
    }

@router.get("/ready")
async def ready():
    # Could check DB + vector store connectivity here
    return {"status": "ready"}
