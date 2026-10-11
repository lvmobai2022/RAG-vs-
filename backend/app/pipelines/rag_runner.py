"""RAG 组共用：检索 → 拒答阈门 →（硬拒答 | 软约束生成 | 正常生成）。"""

from __future__ import annotations

from collections.abc import Callable

from app.config import settings
from app.llm_client import chat_completion
from app.pipelines.common import SYSTEM_PROMPT_RAG, build_rag_user_prompt, chunks_to_citations, timer
from app.pipelines.refusal_gate import (
    apply_soft_constraints_to_prompt,
    build_qualified_refusal,
    evaluate_refusal_gate,
    gate_chunk,
)


def run_rag_pipeline(
    *,
    group: str,
    question: str,
    retrieve_fn: Callable[[], list[dict]],
    system_prompt: str = SYSTEM_PROMPT_RAG,
    expected_evidence_type: str = "",
    chunk_chars: int | None = None,
) -> dict:
    max_chars = chunk_chars if chunk_chars is not None else settings.rag_chunk_chars
    with timer() as t:
        chunks = retrieve_fn()
        gate = evaluate_refusal_gate(
            question,
            chunks,
            expected_evidence_type=expected_evidence_type,
        )

        if gate.action == "hard_refuse":
            answer = build_qualified_refusal(question, gate)
            out_chunks = list(chunks) + [gate_chunk(gate)]
            return {
                "group": group,
                "answer": answer,
                "citations": chunks_to_citations(chunks),
                "retrieved_chunks": out_chunks,
                "latency_ms": t["ms"],
                "refusal_gate": gate.to_dict(),
            }

        user_prompt = build_rag_user_prompt(question, chunks, max_chars=max_chars)
        if gate.action == "soft_constrain":
            user_prompt = apply_soft_constraints_to_prompt(user_prompt, gate)
        answer = chat_completion(system_prompt, user_prompt)
        out_chunks = list(chunks)
        if gate.action == "soft_constrain":
            out_chunks = out_chunks + [gate_chunk(gate)]

    return {
        "group": group,
        "answer": answer,
        "citations": chunks_to_citations(chunks),
        "retrieved_chunks": out_chunks,
        "latency_ms": t["ms"],
        "refusal_gate": gate.to_dict(),
    }
