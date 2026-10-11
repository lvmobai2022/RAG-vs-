"""B 组：正常 RAG —— 向量 Top-K + 拒答阈门。"""

from app.config import settings
from app.pipelines.common import SYSTEM_PROMPT_RAG
from app.pipelines.rag_runner import run_rag_pipeline
from app.retrieval.vectorstore import query_relevant


def run_group_b(
    question: str,
    topic: str | None = None,
    expected_evidence_type: str = "",
) -> dict:
    return run_rag_pipeline(
        group="B",
        question=question,
        retrieve_fn=lambda: query_relevant(question, top_k=settings.rag_top_k, topic=topic),
        system_prompt=SYSTEM_PROMPT_RAG,
        expected_evidence_type=expected_evidence_type,
    )
