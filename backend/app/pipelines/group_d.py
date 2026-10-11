"""D 组：升级 RAG —— 混合多查询检索 + 交叉编码器重排 + 更长上下文 + 覆盖优先。"""

from app.config import settings
from app.pipelines.rag_runner import run_rag_pipeline
from app.retrieval.hybrid import query_upgraded

SYSTEM_PROMPT_RAG_UPGRADED = (
    "你是一名医学健康知识助手，任务是基于下面提供的『检索到的资料』回答用户问题。"
    "这些资料已经过混合检索、证据优先级排序与相关性重排（指南 / 系统综述 / RCT 更靠前，"
    "且与问题细粒度匹配的片段优先）。\n"
    "严格要求：\n"
    "1. 只能依据资料内容作答，不要使用资料之外的知识编造具体数据、试验结论或引用编号；\n"
    "2. 回答中每个关键结论后面用 [编号] 标注对应资料来源；\n"
    "3. 尽量完整抽取资料里与问题相关的全部要点（定义/识别标准/管理原则/证据结论/争议），"
    "按条理组织；宁可多引用资料中的具体表述，也不要只给空泛总结；\n"
    "4. 资料部分相关时：先回答能支撑的部分并标注引用，再用一句话说明哪些细节资料未覆盖；"
    "仅当资料与问题明显无关时才可以拒答；\n"
    "5. 若不同资料结论不一致，必须并列呈现，不要只挑一边；\n"
    "6. 回答语言准确、完整、有条理。"
)


def run_group_d(
    question: str,
    topic: str | None = None,
    expected_evidence_type: str = "",
) -> dict:
    return run_rag_pipeline(
        group="D",
        question=question,
        retrieve_fn=lambda: query_upgraded(
            question,
            top_k=settings.rag_top_k_upgraded,
            topic=topic,
        ),
        system_prompt=SYSTEM_PROMPT_RAG_UPGRADED,
        expected_evidence_type=expected_evidence_type,
        chunk_chars=settings.rag_chunk_chars_upgraded,
    )
