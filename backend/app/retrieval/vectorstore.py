"""基于 Chroma 的向量库封装，统一存放知识库分块，供 B 组正常检索与 C 组降质检索使用。"""

import hashlib

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.config import settings

_client = chromadb.PersistentClient(
    path=settings.chroma_persist_dir,
    settings=ChromaSettings(anonymized_telemetry=False),
)
_embedding_fn = SentenceTransformerEmbeddingFunction(model_name=settings.embedding_model)

_COLLECTION_NAME = "knowledge_base"


def get_collection():
    return _client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=_embedding_fn)


def _make_id(source_id: str) -> str:
    """按 PMID/DOI 全局去重：同一篇文献只保留一条，避免「500 里混进重复导致有效规模塌缩」。"""
    return hashlib.md5(source_id.encode("utf-8")).hexdigest()


def add_documents(topic: str, docs: list[dict]) -> int:
    """把检索到的文献写入向量库，每篇摘要作为一个 chunk。返回实际写入数量。
    空摘要在上游检索阶段已过滤；此处按 source_id 全局去重。
    """
    if not docs:
        return 0
    collection = get_collection()
    seen_ids: set[str] = set()
    ids, texts, metadatas = [], [], []
    for doc in docs:
        source_id = doc.get("source_id") or ""
        if not source_id or not (doc.get("abstract") or "").strip():
            continue
        chunk_id = _make_id(source_id)
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        ids.append(chunk_id)
        texts.append(f"{doc['title']}\n{doc['abstract']}")
        metadatas.append(
            {
                "topic": topic,
                "source": doc["source"],
                "source_id": source_id,
                "title": doc["title"][:500],
                "url": doc.get("url", ""),
                "year": str(doc.get("year", "") or ""),
                "source_type": str(doc.get("source_type", "") or "")[:200],
            }
        )
    if not ids:
        return 0
    collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
    try:
        from app.retrieval.hybrid import invalidate_bm25_cache

        invalidate_bm25_cache()
    except Exception:  # noqa: BLE001
        pass
    return len(ids)


def collection_count() -> int:
    return get_collection().count()


def query_relevant(query_text: str, top_k: int = 5, topic: str | None = None) -> list[dict]:
    """B 组：正常检索，返回和问题最相关的 top_k 个知识库片段。"""
    collection = get_collection()
    where = {"topic": topic} if topic else None
    result = collection.query(query_texts=[query_text], n_results=top_k, where=where)
    return _format_result(result)


def query_degraded(
    query_text: str,
    top_k: int = 5,
    topic: str | None = None,
    noise_ratio: float = 0.6,
) -> list[dict]:
    """C 组：人为降质检索。用一部分不相关话题的噪声片段替换掉本应命中的相关片段，
    模拟"检索质量差"的场景，用于观察 RAG 是否被带偏。
    """
    collection = get_collection()
    noise_count = max(1, round(top_k * noise_ratio))
    relevant_count = max(0, top_k - noise_count)

    relevant_chunks: list[dict] = []
    if relevant_count > 0:
        where = {"topic": topic} if topic else None
        relevant_result = collection.query(query_texts=[query_text], n_results=relevant_count, where=where)
        relevant_chunks = _format_result(relevant_result)

    noise_chunks: list[dict] = []
    where_noise = {"topic": {"$ne": topic}} if topic else None
    noise_result = collection.query(query_texts=[query_text], n_results=noise_count, where=where_noise)
    noise_chunks = _format_result(noise_result)
    for chunk in noise_chunks:
        chunk["is_noise"] = True

    return relevant_chunks + noise_chunks


def _format_result(result: dict) -> list[dict]:
    chunks = []
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for doc, meta, dist in zip(documents, metadatas, distances):
        chunks.append(
            {
                "text": doc,
                "topic": meta.get("topic", ""),
                "source": meta.get("source", ""),
                "source_id": meta.get("source_id", ""),
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "distance": dist,
                "is_noise": False,
            }
        )
    return chunks
