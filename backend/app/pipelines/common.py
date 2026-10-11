"""三组共用的 prompt 构建与耗时计时工具。"""

import time
from contextlib import contextmanager

SYSTEM_PROMPT_PLAIN = (
    "你是一名医学健康知识助手，面向医生、研究者或普通消费者。"
    "请基于你自己的知识直接回答用户的问题，语言准确、简洁、有条理。"
    "如果确实不确定，请明确说明不确定，不要编造具体的文献、试验编号或数据。"
)

SYSTEM_PROMPT_RAG = (
    "你是一名医学健康知识助手，任务是基于下面提供的『检索到的资料』回答用户问题。"
    "严格要求：\n"
    "1. 只能依据资料内容作答，不要使用资料之外的知识编造具体数据、试验结论或引用编号；\n"
    "2. 回答中每个关键结论后面用 [编号] 标注对应资料来源，编号对应资料列表里的序号；\n"
    "3. 如果提供的资料不足以回答问题，或资料内容和问题明显不相关，必须诚实说明『现有资料不足以支持回答』，不要强行给出答案；\n"
    "4. 回答语言准确、简洁、有条理。"
)


def build_rag_user_prompt(question: str, chunks: list[dict], max_chars: int = 800) -> str:
    if not chunks:
        return f"用户问题：{question}\n\n检索到的资料：（无）"
    lines = [f"用户问题：{question}", "", "检索到的资料："]
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(f"[{idx}] 来源：{chunk.get('source_id', '')} 《{chunk.get('title', '')}》")
        lines.append(chunk.get("text", "")[:max_chars])
        lines.append("")
    return "\n".join(lines)


def chunks_to_citations(chunks: list[dict]) -> list[dict]:
    citations = []
    for idx, chunk in enumerate(chunks, start=1):
        citations.append(
            {
                "label": f"[{idx}]",
                "source_id": chunk.get("source_id", ""),
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "is_noise": chunk.get("is_noise", False),
            }
        )
    return citations


@contextmanager
def timer():
    start = time.perf_counter()
    holder = {"ms": 0}
    try:
        yield holder
    finally:
        holder["ms"] = int((time.perf_counter() - start) * 1000)
