"""
PubMed API routes — search live medical literature.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.services.pubmed_service import get_pubmed_service
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/search")
async def search_pubmed(
    q: str = Query(..., min_length=3, description="Search query"),
    max_results: int = Query(5, ge=1, le=20),
    current_user=Depends(get_current_user),
):
    """Search PubMed for medical literature."""
    service = get_pubmed_service()
    articles = await service.search(q, max_results)

    return {
        "query": q,
        "count": len(articles),
        "articles": [
            {
                "pmid": a.pmid,
                "title": a.title,
                "abstract": a.abstract[:500] + "..." if len(a.abstract) > 500 else a.abstract,
                "authors": a.authors,
                "journal": a.journal,
                "year": a.year,
                "doi": a.doi,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{a.pmid}/",
            }
            for a in articles
        ],
    }
