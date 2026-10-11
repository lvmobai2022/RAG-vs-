"""重排模块：优先交叉编码器；不可用时回退到本地向量余弦重排。

召回负责找全，重排负责找准。两种路径都会写入 rerank_score。
"""

from __future__ import annotations

import logging
import math

from app.config import settings

logger = logging.getLogger(__name__)

_cross_encoder = None
_cross_failed = False
_embedder = None
_embed_failed = False


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _get_cross_encoder():
    global _cross_encoder, _cross_failed
    if _cross_failed:
        return None
    if _cross_encoder is not None:
        return _cross_encoder
    try:
        import os

        # 避免坏镜像导致无法读取本地已缓存模型
        if os.environ.get("HF_ENDPOINT", "").rstrip("/") in {
            "https://hf-mirror.com",
            "http://hf-mirror.com",
        }:
            os.environ.pop("HF_ENDPOINT", None)

        from sentence_transformers import CrossEncoder

        logger.info("Loading cross-encoder reranker: %s", settings.rerank_model)
        _cross_encoder = CrossEncoder(settings.rerank_model)
        return _cross_encoder
    except Exception as exc:  # noqa: BLE001
        _cross_failed = True
        logger.warning("Cross-encoder unavailable (%s); will use embedding rerank", exc)
        return None


def _get_embedder():
    global _embedder, _embed_failed
    if _embed_failed:
        return None
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding reranker: %s", settings.embedding_model)
        _embedder = SentenceTransformer(settings.embedding_model)
        return _embedder
    except Exception as exc:  # noqa: BLE001
        _embed_failed = True
        logger.warning("Embedding reranker unavailable: %s", exc)
        return None


def _doc_blob(chunk: dict) -> str:
    title = (chunk.get("title") or "").strip()
    text = (chunk.get("text") or "").strip()
    if title:
        return f"{title}\n{text}"[:1200]
    return text[:1200]


def _rerank_with_cross_encoder(query_text: str, chunks: list[dict]) -> list[dict] | None:
    model = _get_cross_encoder()
    if model is None:
        return None
    pairs = [[query_text, _doc_blob(c)] for c in chunks]
    try:
        scores = model.predict(pairs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cross-encoder predict failed: %s", exc)
        return None
    scored = []
    for chunk, score in zip(chunks, scores):
        item = dict(chunk)
        item["rerank_score"] = float(score)
        item["rerank_method"] = "cross-encoder"
        item["retrieval"] = "hybrid+rerank"
        scored.append(item)
    scored.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return scored


def _rerank_with_embeddings(query_text: str, chunks: list[dict]) -> list[dict] | None:
    """用已有多语言向量模型对「问题 vs 标题+摘要」做余弦重排（无需额外下载交叉编码器）。"""
    model = _get_embedder()
    if model is None:
        return None
    try:
        docs = [_doc_blob(c) for c in chunks]
        q_vec = _l2_normalize(model.encode([query_text], normalize_embeddings=False)[0].tolist())
        doc_vecs = model.encode(docs, normalize_embeddings=False)
        scored = []
        for chunk, vec in zip(chunks, doc_vecs):
            d = _l2_normalize(vec.tolist())
            item = dict(chunk)
            item["rerank_score"] = float(_cosine(q_vec, d))
            item["rerank_method"] = "embedding-cosine"
            item["retrieval"] = "hybrid+rerank"
            scored.append(item)
        scored.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return scored
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding rerank failed: %s", exc)
        return None


def rerank_chunks(
    query_text: str,
    chunks: list[dict],
    *,
    top_k: int | None = None,
) -> list[dict]:
    """对候选 chunks 重排，写入 rerank_score，返回前 top_k。"""
    if not chunks:
        return []
    keep = top_k if top_k is not None else len(chunks)
    if not settings.rerank_enabled or len(chunks) == 1:
        return chunks[:keep]

    backend = (settings.rerank_backend or "embedding").lower().strip()
    scored = None
    if backend in {"cross-encoder", "cross_encoder", "ce"}:
        scored = _rerank_with_cross_encoder(query_text, chunks)
        if scored is None:
            scored = _rerank_with_embeddings(query_text, chunks)
    elif backend == "auto":
        scored = _rerank_with_cross_encoder(query_text, chunks)
        if scored is None:
            scored = _rerank_with_embeddings(query_text, chunks)
    else:
        # embedding：复用已有多语言向量模型
        scored = _rerank_with_embeddings(query_text, chunks)
        if scored is None:
            scored = _rerank_with_cross_encoder(query_text, chunks)

    if scored is None:
        logger.warning("All rerankers failed; keep hybrid order")
        return chunks[:keep]
    return scored[:keep]
