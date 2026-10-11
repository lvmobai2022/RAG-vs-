"""知识库构建脚本：按话题从 PubMed / Europe PMC 抓取文献摘要，写入本地向量库。

检索策略（对应 D1 PPT「先窄后宽」）：
  主题/干预词 + 文献类型(Guideline/Review/RCT) + 出版年(默认 2016-2026)
检索日志写入 backend/data/ingest_log.jsonl，便于报告数据章节复现。

用法：
    python -m scripts.ingest
    python -m scripts.ingest --per-source 40
    python -m scripts.ingest --reset   # 清空后重建（切换全局去重策略时建议使用）
    python -m scripts.ingest --topic 高血压 --query "hypertension guideline antihypertensive"
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.retrieval.europepmc import build_europepmc_query, search_europepmc  # noqa: E402
from app.retrieval.pubmed import build_pubmed_query, search_pubmed  # noqa: E402
# 注意：不要在这里 import vectorstore——PersistentClient 会锁住 chroma 文件，
# 导致 --reset 时 shutil.rmtree 失败。vectorstore 在 reset 之后再懒加载。

# 每个话题可配多条 query，扩大覆盖面；正式报告以 README 中的检索式版本为准
DEFAULT_TOPICS = [
    {
        "topic": "高血压",
        "queries": [
            "hypertension antihypertensive medication adherence guideline",
            "hypertension blood pressure target randomized controlled trial",
            "resistant hypertension management systematic review",
        ],
    },
    {
        "topic": "血脂",
        "queries": [
            "dyslipidemia statin lifestyle intervention cardiovascular risk",
            "omega-3 fish oil cardiovascular secondary prevention randomized trial",
            "LDL cholesterol lowering guideline systematic review",
        ],
    },
    {
        "topic": "糖尿病",
        "queries": [
            "type 2 diabetes management guideline lifestyle intervention",
            "exercise intervention type 2 diabetes glycemic control randomized trial",
            "intermittent fasting type 2 diabetes systematic review",
        ],
    },
    {
        "topic": "地中海饮食",
        "queries": [
            "mediterranean diet cardiovascular disease risk randomized trial",
            "PREDIMED mediterranean diet cardiovascular events",
        ],
    },
    {
        "topic": "限钠饮食",
        "queries": [
            "sodium restriction diet blood pressure randomized controlled trial",
            "dietary sodium reduction hypertension systematic review meta-analysis",
        ],
    },
    {
        "topic": "抗凝治疗",
        "queries": [
            "anticoagulant warfarin DOAC mechanism guideline",
            "direct oral anticoagulant atrial fibrillation randomized trial",
        ],
    },
    {
        "topic": "心血管预防",
        "queries": [
            "aspirin primary prevention cardiovascular disease guideline bleeding risk",
            "cardiovascular disease primary prevention lifestyle guideline",
        ],
    },
    {
        "topic": "维生素D",
        "queries": [
            "vitamin D supplementation fracture cardiovascular disease randomized trial VITAL",
            "vitamin D deficiency bone health systematic review",
        ],
    },
    {
        "topic": "饮食与癌症风险",
        "queries": [
            "red meat processed meat colorectal cancer risk epidemiology",
            "processed meat colorectal cancer IARC systematic review",
        ],
    },
    {
        "topic": "运动干预",
        "queries": [
            "physical activity type 2 diabetes glycemic control meta-analysis",
            "resistance training hypertension blood pressure randomized trial",
        ],
    },
    {
        "topic": "低碳水饮食",
        "queries": [
            "low carbohydrate diet cardiovascular risk long term outcome",
            "ketogenic diet type 2 diabetes randomized controlled trial",
        ],
    },
    {
        "topic": "低脂饮食",
        "queries": [
            "low fat diet cardiovascular disease prevention randomized trial",
            "dietary fat type cardiovascular risk guideline",
        ],
    },
]

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "ingest_log.jsonl"


def _append_log(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def ingest_query(topic: str, query: str, per_source: int = 35) -> int:
    from app.retrieval.vectorstore import add_documents, collection_count

    print(f"[ingest] 话题「{topic}」检索中... query={query}")
    pubmed_term = build_pubmed_query(query)
    epmc_term = build_europepmc_query(query)
    docs = []
    pubmed_hits = 0
    epmc_hits = 0

    try:
        pubmed_docs = search_pubmed(query, retmax=per_source)
        pubmed_hits = pubmed_docs[0]["hit_count"] if pubmed_docs else 0
        docs += pubmed_docs
        print(f"  PubMed 命中约 {pubmed_hits}，取回有效摘要 {len(pubmed_docs)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  PubMed 检索失败：{exc}")
    time.sleep(0.4)

    try:
        epmc_docs = search_europepmc(query, page_size=per_source)
        epmc_hits = epmc_docs[0]["hit_count"] if epmc_docs else 0
        docs += epmc_docs
        print(f"  Europe PMC 命中约 {epmc_hits}，取回有效摘要 {len(epmc_docs)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  Europe PMC 检索失败：{exc}")

    written = add_documents(topic, docs)
    print(f"  -> 本批写入/更新 {written} 条（全局 PMID/DOI 去重后）")

    _append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": topic,
            "base_query": query,
            "pubmed_query": pubmed_term,
            "europepmc_query": epmc_term,
            "mindate": "2016",
            "maxdate": "2026",
            "publication_types": ["Guideline", "Review", "Systematic Review", "Meta-Analysis", "RCT"],
            "per_source": per_source,
            "pubmed_hit_count": pubmed_hits,
            "europepmc_hit_count": epmc_hits,
            "fetched_with_abstract": len(docs),
            "written": written,
            "collection_count_after": collection_count(),
        }
    )
    return written


def ingest_topic(topic: str, query: str, per_source: int = 35) -> int:
    return ingest_query(topic, query, per_source=per_source)


def main():
    parser = argparse.ArgumentParser(description="构建知识库向量库")
    parser.add_argument("--topic", type=str, help="单个话题名称")
    parser.add_argument("--query", type=str, help="对应的检索关键词（英文效果更好）")
    parser.add_argument("--config", type=str, help="批量话题配置 JSON，格式 [{topic, query|queries}, ...]")
    parser.add_argument("--per-source", type=int, default=35, help="每个数据源每次抓取数量")
    parser.add_argument("--reset", action="store_true", help="清空本地向量库后重建")
    args = parser.parse_args()

    if args.reset:
        chroma_dir = Path(settings.chroma_persist_dir)
        if chroma_dir.exists():
            for attempt in range(5):
                try:
                    shutil.rmtree(chroma_dir)
                    break
                except PermissionError:
                    time.sleep(1.5)
                    if attempt == 4:
                        raise
            print(f"[ingest] 已清空向量库目录：{chroma_dir}")
        if LOG_PATH.exists():
            LOG_PATH.unlink()
            print("[ingest] 已清空旧检索日志")

    jobs: list[tuple[str, str]] = []
    if args.topic and args.query:
        jobs = [(args.topic, args.query)]
    elif args.config:
        items = json.loads(Path(args.config).read_text(encoding="utf-8"))
        for item in items:
            qs = item.get("queries") or [item["query"]]
            for q in qs:
                jobs.append((item["topic"], q))
    else:
        print("[ingest] 使用内置默认话题列表（含多 query）")
        for item in DEFAULT_TOPICS:
            for q in item["queries"]:
                jobs.append((item["topic"], q))

    from app.retrieval.vectorstore import collection_count

    total_written = 0
    for topic, query in jobs:
        total_written += ingest_query(topic, query, per_source=args.per_source)
        time.sleep(0.3)

    final_count = collection_count()
    print(f"[ingest] 完成：本轮写入/更新合计 {total_written}，知识库当前有效规模 {final_count}")
    if final_count < 500:
        print("[ingest] 提示：尚未达到 PPT 基础档 ≥500，可提高 --per-source 或再跑一轮补充 query")
    else:
        print("[ingest] 已达到/超过 PPT 基础档 ≥500")


if __name__ == "__main__":
    main()
