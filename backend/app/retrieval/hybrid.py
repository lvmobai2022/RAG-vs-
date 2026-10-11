"""升级 RAG 检索：向量召回 + BM25 关键词召回 + RRF 融合 + 证据类型加权 + MMR 去冗余。

对应课程进阶项里的「混合检索 / 更完整评估」：作为第 D 组对照臂，
相对 B 组「纯向量 Top-K」提升相关文献召回与证据优先级。
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from app.retrieval.vectorstore import get_collection

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")

# 证据类型加权：指南 / 系统综述 / RCT 优先于普通文章
_TYPE_BOOST = {
    "guideline": 0.18,
    "practice guideline": 0.18,
    "systematic review": 0.15,
    "meta-analysis": 0.15,
    "meta analysis": 0.15,
    "randomized controlled trial": 0.12,
    "clinical trial": 0.08,
    "review": 0.05,
}

_bm25_cache: dict | None = None


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


class _BM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus_tokens
        self.N = len(corpus_tokens)
        self.doc_len = [len(doc) for doc in corpus_tokens]
        self.avgdl = sum(self.doc_len) / self.N if self.N else 0.0
        self.df: Counter[str] = Counter()
        for doc in corpus_tokens:
            for term in set(doc):
                self.df[term] += 1

    def score(self, query_tokens: list[str], index: int) -> float:
        if not query_tokens or self.N == 0:
            return 0.0
        doc = self.corpus[index]
        if not doc:
            return 0.0
        tf = Counter(doc)
        score = 0.0
        dl = self.doc_len[index]
        for term in query_tokens:
            if term not in tf:
                continue
            n_q = self.df.get(term, 0)
            idf = math.log(1 + (self.N - n_q + 0.5) / (n_q + 0.5))
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            score += idf * (freq * (self.k1 + 1)) / (denom or 1.0)
        return score


def _load_bm25_index(force: bool = False) -> dict:
    global _bm25_cache
    collection = get_collection()
    count = collection.count()
    if (
        not force
        and _bm25_cache is not None
        and _bm25_cache.get("count") == count
    ):
        return _bm25_cache

    batch_data = collection.get(include=["documents", "metadatas"])
    ids = batch_data.get("ids") or []
    documents = batch_data.get("documents") or []
    metadatas = batch_data.get("metadatas") or []
    tokens = [_tokenize(doc) for doc in documents]
    _bm25_cache = {
        "count": count,
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
        "bm25": _BM25(tokens),
    }
    return _bm25_cache


def _type_boost(source_type: str) -> float:
    text = (source_type or "").lower()
    boost = 0.0
    for key, value in _TYPE_BOOST.items():
        if key in text:
            boost = max(boost, value)
    return boost


def _rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranks in rank_lists:
        for rank, doc_id in enumerate(ranks, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return scores


def _mmr_select(
    candidate_ids: list[str],
    id_to_vec_rank: dict[str, int],
    id_to_text: dict[str, str],
    top_k: int,
    lambda_mult: float = 0.7,
) -> list[str]:
    """用简易词袋 Jaccard 做 MMR，减少 Top-K 里标题/摘要高度重复的片段。"""
    if not candidate_ids:
        return []

    def jaccard(a: str, b: str) -> float:
        ta, tb = set(_tokenize(a)), set(_tokenize(b))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    selected: list[str] = []
    remaining = candidate_ids[:]
    while remaining and len(selected) < top_k:
        best_id = None
        best_score = -1e9
        for doc_id in remaining:
            relevance = 1.0 / (id_to_vec_rank.get(doc_id, 100) + 1)
            diversity = 0.0
            if selected:
                diversity = max(jaccard(id_to_text[doc_id], id_to_text[s]) for s in selected)
            score = lambda_mult * relevance - (1 - lambda_mult) * diversity
            if score > best_score:
                best_score = score
                best_id = doc_id
        selected.append(best_id)  # type: ignore[arg-type]
        remaining.remove(best_id)
    return selected


def _query_variants(query_text: str) -> list[str]:
    """多查询：原文 + 拉丁术语串，提升中英混合医学问题的召回。"""
    variants = [query_text]
    latin = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", query_text or ""))
    if latin and latin.lower() not in (query_text or "").lower():
        variants.append(latin)
    # 常见中文主题的轻量英文扩展（不替代原文，只追加一路召回）
    q = query_text or ""
    extra: list[str] = []
    if "难治" in q or "耐药" in q:
        extra.append("resistant hypertension diagnosis management adherence")
    if "他汀" in q or "血脂" in q:
        extra.append("statin dyslipidemia safety management review")
    if "糖尿病" in q or "血糖" in q:
        extra.append("type 2 diabetes diagnosis HbA1c guideline")
    if "抗凝" in q or "DOAC" in q or "华法林" in q:
        extra.append("DOAC versus vitamin K antagonist bleeding thrombosis meta-analysis")
    if "地中海" in q:
        extra.append("Mediterranean diet cardiovascular prevention mechanisms")
    if "限钠" in q or "减盐" in q:
        extra.append("sodium reduction blood pressure systematic review")
    if "运动" in q or "有氧" in q or "抗阻" in q:
        extra.append("exercise training blood pressure glycemic control randomized trial")
    if "阿司匹林" in q or "一级预防" in q:
        extra.append("aspirin primary prevention cardiovascular bleeding risk")
    if "维生素D" in q or "维生素 D" in q:
        extra.append("vitamin D supplementation fracture cardiovascular VITAL trial")
    if "红肉" in q or "加工肉" in q:
        extra.append("red processed meat colorectal cancer systematic review")
    if "低碳水" in q or "断食" in q or "生酮" in q:
        extra.append("low carbohydrate ketogenic intermittent fasting metabolic outcomes")
    if "低脂" in q:
        extra.append("low fat diet cardiovascular prevention dietary pattern")
    if "鱼油" in q or "ω-3" in q or "omega" in q.lower():
        extra.append("omega-3 fish oil cardiovascular secondary prevention trial")
    for e in extra:
        if e not in variants:
            variants.append(e)
    return variants[:4]


def query_upgraded(query_text: str, top_k: int = 5, topic: str | None = None) -> list[dict]:
    """D 组升级检索：多查询向量 + BM25 → RRF → 类型加权 → 交叉编码器重排 → Top-K。"""
    from app.retrieval.rerank import rerank_chunks

    collection = get_collection()
    if collection.count() == 0:
        return []

    candidate_n = max(top_k * 8, 40)
    where = {"topic": topic} if topic else None
    id_to_chunk: dict[str, dict] = {}
    rank_lists: list[list[str]] = []

    # 1) 多查询向量召回
    for q in _query_variants(query_text):
        vector_result = collection.query(
            query_texts=[q],
            n_results=min(candidate_n, max(collection.count(), 1)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        vec_ids = (vector_result.get("ids") or [[]])[0]
        vec_docs = (vector_result.get("documents") or [[]])[0]
        vec_metas = (vector_result.get("metadatas") or [[]])[0]
        vec_dists = (vector_result.get("distances") or [[]])[0]
        rank_lists.append(vec_ids)
        for doc_id, doc, meta, dist in zip(vec_ids, vec_docs, vec_metas, vec_dists):
            prev = id_to_chunk.get(doc_id)
            # 保留更小（更好）的向量距离
            if prev is None or (isinstance(dist, (int, float)) and dist < prev.get("distance", 1e9)):
                id_to_chunk[doc_id] = {
                    "text": doc,
                    "topic": meta.get("topic", ""),
                    "source": meta.get("source", ""),
                    "source_id": meta.get("source_id", ""),
                    "title": meta.get("title", ""),
                    "url": meta.get("url", ""),
                    "year": meta.get("year", ""),
                    "source_type": meta.get("source_type", ""),
                    "distance": dist,
                    "is_noise": False,
                    "retrieval": "hybrid",
                }

    # 2) BM25 召回（对每个 query variant 取分后合并）
    index = _load_bm25_index()
    bm25_best: dict[str, float] = {}
    for q in _query_variants(query_text):
        q_tokens = _tokenize(q)
        for i, doc_id in enumerate(index["ids"]):
            meta = index["metadatas"][i] or {}
            if topic and meta.get("topic") != topic:
                continue
            score = index["bm25"].score(q_tokens, i)
            if score <= 0:
                continue
            if score > bm25_best.get(doc_id, 0.0):
                bm25_best[doc_id] = score
            if doc_id not in id_to_chunk:
                id_to_chunk[doc_id] = {
                    "text": index["documents"][i],
                    "topic": meta.get("topic", ""),
                    "source": meta.get("source", ""),
                    "source_id": meta.get("source_id", ""),
                    "title": meta.get("title", ""),
                    "url": meta.get("url", ""),
                    "year": meta.get("year", ""),
                    "source_type": meta.get("source_type", ""),
                    "distance": 999.0,
                    "is_noise": False,
                    "retrieval": "hybrid",
                }
    bm25_ranks = [doc_id for doc_id, _ in sorted(bm25_best.items(), key=lambda x: x[1], reverse=True)[:candidate_n]]
    rank_lists.append(bm25_ranks)

    # 3) RRF 融合 + 证据类型加权
    fused = _rrf_fuse(rank_lists)
    for doc_id, chunk in id_to_chunk.items():
        fused[doc_id] = fused.get(doc_id, 0.0) + _type_boost(chunk.get("source_type", ""))

    ranked_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)
    ranked_ids = [doc_id for doc_id in ranked_ids if doc_id in id_to_chunk][: max(candidate_n, top_k)]

    # 4) 取融合 Top-N 候选，做交叉编码器重排（找准）
    from app.config import settings as _settings

    pool_n = max(top_k, min(_settings.rerank_candidates, len(ranked_ids)))
    # 先用轻量 MMR 控制池子冗余，再重排
    primary_vec = rank_lists[0] if rank_lists else []
    id_to_vec_rank = {doc_id: i for i, doc_id in enumerate(primary_vec, start=1)}
    id_to_text = {doc_id: id_to_chunk[doc_id].get("text", "") for doc_id in ranked_ids}
    pool_ids = _mmr_select(ranked_ids, id_to_vec_rank, id_to_text, top_k=pool_n, lambda_mult=0.75)

    pool_chunks = []
    for doc_id in pool_ids:
        chunk = dict(id_to_chunk[doc_id])
        chunk["hybrid_score"] = round(fused.get(doc_id, 0.0), 5)
        pool_chunks.append(chunk)

    # 5) 重排后取最终 Top-K
    return rerank_chunks(query_text, pool_chunks, top_k=top_k)


def invalidate_bm25_cache() -> None:
    global _bm25_cache
    _bm25_cache = None
