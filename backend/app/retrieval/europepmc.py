"""Europe PMC RESTful API 检索封装。"""

import httpx

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

PUBLICATION_TYPE_FILTER = (
    '(PUB_TYPE:"Review" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta Analysis" '
    'OR PUB_TYPE:"Guideline" OR PUB_TYPE:"Practice Guideline" '
    'OR PUB_TYPE:"Randomized Controlled Trial")'
)


def build_europepmc_query(query: str, mindate: str = "2016", maxdate: str = "2026") -> str:
    """组装可复现的 Europe PMC 检索式：主题/干预词 + 文献类型 + 首发日期。"""
    return f"({query}) AND {PUBLICATION_TYPE_FILTER} AND FIRST_PDATE:[{mindate}-01-01 TO {maxdate}-12-31]"


def search_europepmc(
    query: str,
    page_size: int = 30,
    *,
    mindate: str = "2016",
    maxdate: str = "2026",
    apply_filters: bool = True,
    page: int = 1,
) -> list[dict]:
    """按关键词检索 Europe PMC。空摘要会被跳过。"""
    term = build_europepmc_query(query, mindate=mindate, maxdate=maxdate) if apply_filters else query
    with httpx.Client(timeout=40) as client:
        resp = client.get(
            SEARCH_URL,
            params={
                "query": term,
                "format": "json",
                "pageSize": page_size,
                "page": page,
                "resultType": "core",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        hit_count = int(payload.get("hitCount", 0) or 0)
        results = payload.get("resultList", {}).get("result", [])

    docs = []
    for item in results:
        abstract = item.get("abstractText", "") or ""
        if not abstract.strip():
            continue
        pmid = item.get("pmid", "")
        doi = item.get("doi", "")
        source_id = f"PMID:{pmid}" if pmid else (f"DOI:{doi}" if doi else f"EPMC:{item.get('id', '')}")
        pub_type = item.get("pubType", "") or item.get("pubTypeList", {}).get("pubType", "")
        if isinstance(pub_type, list):
            pub_type = "; ".join(str(x) for x in pub_type)
        docs.append(
            {
                "source": "europepmc",
                "source_id": source_id,
                "title": item.get("title", "(无标题)"),
                "abstract": abstract.strip(),
                "url": f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}",
                "year": str(item.get("pubYear", "") or ""),
                "source_type": str(pub_type) or "Article",
                "query_used": term,
                "hit_count": hit_count,
            }
        )
    return docs
