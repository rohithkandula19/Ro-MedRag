"""
Evaluation API — run RAG quality assessments.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.services.eval_service import get_evaluator
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class EvalRequest(BaseModel):
    test_queries: Optional[List[dict]] = None
    document_ids: Optional[List[str]] = None


class SingleEvalRequest(BaseModel):
    query: str
    expected_keywords: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None


@router.post("/run")
async def run_eval_suite(
    body: EvalRequest,
    current_user=Depends(get_current_user),
):
    """Run full evaluation suite against the RAG pipeline."""
    evaluator = get_evaluator()
    result = await evaluator.run_eval_suite(
        test_queries=body.test_queries,
        document_ids=body.document_ids,
    )

    return {
        "timestamp": result.timestamp,
        "total_queries": result.total_queries,
        "pass_rate": result.pass_rate,
        "metrics": {
            "avg_faithfulness": result.avg_faithfulness,
            "avg_answer_relevancy": result.avg_answer_relevancy,
            "avg_context_precision": result.avg_context_precision,
            "avg_citation_accuracy": result.avg_citation_accuracy,
        },
        "performance": {
            "avg_latency_ms": result.avg_latency_ms,
            "total_tokens": result.total_tokens,
        },
        "results": [
            {
                "query": r.query,
                "answer": r.answer[:200] + "..." if len(r.answer) > 200 else r.answer,
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "citation_accuracy": r.citation_accuracy,
                "latency_ms": r.latency_ms,
                "tokens_used": r.tokens_used,
                "chunks_retrieved": r.chunks_retrieved,
                "insufficient_evidence": r.insufficient_evidence,
            }
            for r in result.results
        ],
    }


@router.post("/single")
async def eval_single_query(
    body: SingleEvalRequest,
    current_user=Depends(get_current_user),
):
    """Evaluate a single query."""
    evaluator = get_evaluator()
    result = await evaluator.evaluate_single(
        query=body.query,
        expected_keywords=body.expected_keywords,
        document_ids=body.document_ids,
    )

    return {
        "query": result.query,
        "answer": result.answer,
        "metrics": {
            "faithfulness": result.faithfulness,
            "answer_relevancy": result.answer_relevancy,
            "context_precision": result.context_precision,
            "citation_accuracy": result.citation_accuracy,
        },
        "performance": {
            "latency_ms": result.latency_ms,
            "tokens_used": result.tokens_used,
            "chunks_retrieved": result.chunks_retrieved,
        },
        "insufficient_evidence": result.insufficient_evidence,
    }
