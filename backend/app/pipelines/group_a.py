"""A 组：纯通用大模型，不做任何检索增强。"""

from app.llm_client import chat_completion
from app.pipelines.common import SYSTEM_PROMPT_PLAIN, timer


def run_group_a(question: str) -> dict:
    with timer() as t:
        answer = chat_completion(SYSTEM_PROMPT_PLAIN, question)
    return {
        "group": "A",
        "answer": answer,
        "citations": [],
        "retrieved_chunks": [],
        "latency_ms": t["ms"],
    }
