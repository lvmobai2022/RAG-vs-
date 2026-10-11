"""PubMed E-utilities 检索封装（esearch + efetch）。"""

import xml.etree.ElementTree as ET

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# 文献类型过滤：指南 / 综述 / RCT，对应 PPT「主题词 + 干预词 + 年限 + 文献类型」策略
PUBLICATION_TYPE_FILTER = (
    '("Guideline"[Publication Type] OR "Practice Guideline"[Publication Type] '
    'OR "Review"[Publication Type] OR "Systematic Review"[Publication Type] '
    'OR "Meta-Analysis"[Publication Type] '
    'OR "Randomized Controlled Trial"[Publication Type])'
)


def build_pubmed_query(query: str, mindate: str = "2016", maxdate: str = "2026") -> str:
    """组装可复现的 PubMed 检索式：主题/干预词 + 文献类型 + 出版年。"""
    return f"({query}) AND {PUBLICATION_TYPE_FILTER} AND ({mindate}:{maxdate}[Date - Publication])"


def search_pubmed(
    query: str,
    retmax: int = 30,
    *,
    mindate: str = "2016",
    maxdate: str = "2026",
    apply_filters: bool = True,
) -> list[dict]:
    """按关键词检索 PubMed，返回带 year / source_type 的文献摘要列表。空摘要会被跳过。"""
    term = build_pubmed_query(query, mindate=mindate, maxdate=maxdate) if apply_filters else query
    with httpx.Client(timeout=40) as client:
        esearch_resp = client.get(
            ESEARCH_URL,
            params={
                "db": "pubmed",
                "term": term,
                "retmax": retmax,
                "retmode": "json",
                "sort": "relevance",
            },
        )
        esearch_resp.raise_for_status()
        payload = esearch_resp.json().get("esearchresult", {})
        id_list = payload.get("idlist", [])
        hit_count = int(payload.get("count", 0) or 0)
        if not id_list:
            return []

        efetch_resp = client.get(
            EFETCH_URL,
            params={"db": "pubmed", "id": ",".join(id_list), "rettype": "abstract", "retmode": "xml"},
        )
        efetch_resp.raise_for_status()
        docs = _parse_pubmed_xml(efetch_resp.text)
        for doc in docs:
            doc["query_used"] = term
            doc["hit_count"] = hit_count
        return docs


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    docs = []
    root = ET.fromstring(xml_text)
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abstract_parts = article.findall(".//AbstractText")
        year_el = article.find(".//PubDate/Year")
        medline_year = article.find(".//MedlineDate")
        pub_types = [pt.text or "" for pt in article.findall(".//PublicationType")]

        pmid = pmid_el.text if pmid_el is not None else ""
        title = "".join(title_el.itertext()).strip() if title_el is not None else "(无标题)"
        abstract = " ".join("".join(p.itertext()).strip() for p in abstract_parts).strip()
        if not abstract:
            continue

        year = ""
        if year_el is not None and year_el.text:
            year = year_el.text
        elif medline_year is not None and medline_year.text:
            year = medline_year.text[:4]

        docs.append(
            {
                "source": "pubmed",
                "source_id": f"PMID:{pmid}",
                "title": title or "(无标题)",
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "year": year,
                "source_type": "; ".join([p for p in pub_types if p]) or "Article",
            }
        )
    return docs
