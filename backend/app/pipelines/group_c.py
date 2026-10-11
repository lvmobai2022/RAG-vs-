"""C 组：降质 RAG —— 噪声检索 + 拒答阈门（观察阈门是否挡住被噪声带偏）。"""

from app.config import settings
from app.pipelines.common import SYSTEM_PROMPT_RAG
from app.pipelines.rag_runner import run_rag_pipeline
from app.retrieval.vectorstore import query_degraded


def run_group_c(
    question: str,
    topic: str | None = None,
    expected_evidence_type: str = "",
) -> dict:
    return run_rag_pipeline(
        group="C",
        question=question,
        retrieve_fn=lambda: query_degraded(
            question,
            top_k=settings.degraded_top_k,
            topic=topic,
            noise_ratio=settings.degraded_noise_ratio,
        ),
        system_prompt=SYSTEM_PROMPT_RAG,
        expected_evidence_type=expected_evidence_type,
    )
