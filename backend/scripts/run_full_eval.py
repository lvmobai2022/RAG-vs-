"""批量跑完全部题库的 A/B/C/D 对比，并把汇总结果回填到 EVALUATION_REPORT.md。"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
REPORT = Path(__file__).resolve().parents[2] / "EVALUATION_REPORT.md"
GROUPS = ["A", "B", "C", "D"]


def pct(v) -> str:
    if v is None:
        return "—"
    return f"{round(float(v) * 100)}%"


def num(v, digits: int = 3) -> str:
    if v is None:
        return "—"
    return str(round(float(v), digits))


def reset_runs() -> None:
    """清空历史运行/评判，保证本次重跑统计干净。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.db import SessionLocal, init_db
    from app import models

    init_db()
    db = SessionLocal()
    try:
        n_eval = db.query(models.AutoEvaluation).delete()
        n_run = db.query(models.RunResult).delete()
        db.commit()
        print(f"[eval] 已清空历史记录：runs={n_run}, evals={n_eval}")
    finally:
        db.close()


def run_all():
    qs = requests.get(f"{BASE}/api/questions", timeout=30).json()
    print(f"[eval] 共 {len(qs)} 道题，开始批量运行（每题 A/B/C/D + 自动评判）...")
    ok, fail = 0, 0
    for i, q in enumerate(qs, 1):
        qid = q["id"]
        print(f"\n[{i}/{len(qs)}] Q{qid} [{q.get('track','')}] {q['text'][:40]}...")
        t0 = time.time()
        try:
            r = requests.post(
                f"{BASE}/api/runs",
                json={"question_id": qid, "groups": GROUPS},
                timeout=420,
            )
            if r.status_code != 200:
                print(f"  FAIL {r.status_code}: {r.text[:200]}")
                fail += 1
                continue
            results = r.json()
            for item in results:
                ev = item.get("auto_evaluation") or {}
                print(
                    f"  {item['group']}: refusal={ev.get('is_refusal')} "
                    f"correct={ev.get('correctness_verdict')} "
                    f"complete={ev.get('completeness_rate')} "
                    f"cite={ev.get('citation_support_rate')} "
                    f"err={ev.get('judge_error') or '-'}"
                )
            ok += 1
            print(f"  用时 {time.time()-t0:.0f}s")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")
            fail += 1
    print(f"\n[eval] 完成：成功 {ok}，失败 {fail}")
    return ok, fail


def fetch_summary():
    return requests.get(f"{BASE}/api/stats/summary", timeout=30).json()


def fill_report(summary: list[dict]):
    by_group = {row["group"]: row for row in summary}

    def cell(group: str, key: str, kind: str = "num") -> str:
        row = by_group.get(group) or {}
        v = row.get(key)
        if kind == "pct":
            return pct(v)
        if kind == "int":
            return str(int(v)) if v is not None else "—"
        return num(v)

    table = f"""| 指标 | A 裸 LLM | B 正常 RAG | C 劣化 RAG | D 升级 RAG |
| --- | --- | --- | --- | --- |
| 运行次数 | {cell('A','run_count','int')} | {cell('B','run_count','int')} | {cell('C','run_count','int')} | {cell('D','run_count','int')} |
| 正确性得分 | {cell('A','correctness_score')} | {cell('B','correctness_score')} | {cell('C','correctness_score')} | {cell('D','correctness_score')} |
| 完整性覆盖率 | {cell('A','completeness_rate','pct')} | {cell('B','completeness_rate','pct')} | {cell('C','completeness_rate','pct')} | {cell('D','completeness_rate','pct')} |
| 清晰度 | {cell('A','clarity_score')} | {cell('B','clarity_score')} | {cell('C','clarity_score')} | {cell('D','clarity_score')} |
| 引用支撑率 | {cell('A','citation_support_rate','pct')} | {cell('B','citation_support_rate','pct')} | {cell('C','citation_support_rate','pct')} | {cell('D','citation_support_rate','pct')} |
| 无效引用编号率 | {cell('A','invalid_citation_rate','pct')} | {cell('B','invalid_citation_rate','pct')} | {cell('C','invalid_citation_rate','pct')} | {cell('D','invalid_citation_rate','pct')} |
| 安全违规率 | {cell('A','safety_violation_rate','pct')} | {cell('B','safety_violation_rate','pct')} | {cell('C','safety_violation_rate','pct')} | {cell('D','safety_violation_rate','pct')} |
| 应拒答召回率 | {cell('A','abstain_recall','pct')} | {cell('B','abstain_recall','pct')} | {cell('C','abstain_recall','pct')} | {cell('D','abstain_recall','pct')} |
| 误拒率 | {cell('A','over_refusal_rate','pct')} | {cell('B','over_refusal_rate','pct')} | {cell('C','over_refusal_rate','pct')} | {cell('D','over_refusal_rate','pct')} |"""

    a, b, c, d = (by_group.get(g, {}) for g in GROUPS)

    def better_lower(x, y):
        if x is None or y is None:
            return None
        return x < y

    def better_higher(x, y):
        if x is None or y is None:
            return None
        return x > y

    h1_parts = []
    if a.get("citation_support_rate") is None and b.get("citation_support_rate") is not None:
        h1 = True
        h1_parts.append("A 无外部引用可核验，B 有可支撑引用")
    else:
        cite_ok = better_higher(b.get("citation_support_rate"), a.get("citation_support_rate"))
        inv_ok = better_lower(b.get("invalid_citation_rate") or 0, a.get("invalid_citation_rate") or 0)
        h1 = bool(cite_ok or inv_ok)
        h1_parts.append(
            f"B引用支撑={pct(b.get('citation_support_rate'))} vs A={pct(a.get('citation_support_rate'))}; "
            f"无效引用 B={pct(b.get('invalid_citation_rate'))} vs A={pct(a.get('invalid_citation_rate'))}"
        )

    h2_comp = better_lower(c.get("completeness_rate"), b.get("completeness_rate"))
    h2_corr = better_lower(c.get("correctness_score"), b.get("correctness_score"))
    h2_cite = better_lower(c.get("citation_support_rate"), b.get("citation_support_rate"))
    h2 = bool(h2_comp or h2_corr or h2_cite)
    h2_detail = (
        f"完整性 C={pct(c.get('completeness_rate'))} vs B={pct(b.get('completeness_rate'))}; "
        f"正确性 C={num(c.get('correctness_score'))} vs B={num(b.get('correctness_score'))}; "
        f"引用支撑 C={pct(c.get('citation_support_rate'))} vs B={pct(b.get('citation_support_rate'))}"
    )

    def recall(g):
        return g.get("abstain_recall")

    h3 = True
    h3_notes = []
    for name, g in [("B", b), ("C", c), ("D", d)]:
        if recall(g) is not None and recall(a) is not None and recall(g) + 1e-9 < recall(a):
            h3 = False
            h3_notes.append(f"{name}召回({pct(recall(g))})低于A({pct(recall(a))})")
    for name, g in [("B", b), ("C", c), ("D", d)]:
        if g.get("over_refusal_rate") is not None and g["over_refusal_rate"] > 0.4:
            h3 = False
            h3_notes.append(f"{name}误拒率过高({pct(g.get('over_refusal_rate'))})")
    if not h3_notes:
        h3_notes.append(
            f"召回 A/B/C/D={pct(recall(a))}/{pct(recall(b))}/{pct(recall(c))}/{pct(recall(d))}; "
            f"误拒 A/B/C/D={pct(a.get('over_refusal_rate'))}/{pct(b.get('over_refusal_rate'))}/"
            f"{pct(c.get('over_refusal_rate'))}/{pct(d.get('over_refusal_rate'))}"
        )

    # H4: 升级 RAG 相对 B 至少在一项关键质量上不更差，且误拒不显著更高
    h4_better = bool(
        better_higher(d.get("completeness_rate"), b.get("completeness_rate"))
        or better_higher(d.get("correctness_score"), b.get("correctness_score"))
        or better_higher(d.get("citation_support_rate"), b.get("citation_support_rate"))
        or better_lower(d.get("over_refusal_rate"), b.get("over_refusal_rate"))
    )
    h4_not_worse_cite = True
    if d.get("citation_support_rate") is not None and b.get("citation_support_rate") is not None:
        h4_not_worse_cite = d["citation_support_rate"] + 1e-9 >= b["citation_support_rate"] - 0.05
    h4 = bool(h4_better and h4_not_worse_cite)
    h4_detail = (
        f"完整性 D={pct(d.get('completeness_rate'))} vs B={pct(b.get('completeness_rate'))}; "
        f"正确性 D={num(d.get('correctness_score'))} vs B={num(b.get('correctness_score'))}; "
        f"引用支撑 D={pct(d.get('citation_support_rate'))} vs B={pct(b.get('citation_support_rate'))}; "
        f"误拒 D={pct(d.get('over_refusal_rate'))} vs B={pct(b.get('over_refusal_rate'))}"
    )

    def mark(ok: bool) -> str:
        return "成立" if ok else "不成立"

    h1_text = " ".join(h1_parts)
    h3_text = "; ".join(h3_notes)
    hypo = (
        "### 假设判定（基于本次全量跑分自动汇总）\n\n"
        f"- [x] H1 {mark(h1)}：{h1_text}\n"
        f"- [x] H2 {mark(h2)}：{h2_detail}\n"
        f"- [x] H3 {mark(h3)}：{h3_text}\n"
        f"- [x] H4 {mark(h4)}（升级RAG优于/不弱于正常RAG）：{h4_detail}\n"
    )

    text = REPORT.read_text(encoding="utf-8")
    text = re.sub(
        r"\| 指标 \| A 裸 LLM \| B 正常 RAG \| C 劣化 RAG(?: \| D 升级 RAG)? \|\n\| --- \| --- \| --- \| --- \|(?: \| ---)? \|\n(?:\|.*\|\n)+?\| 误拒率 \|.*?\|",
        table + "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"### 假设判定（(?:演示时勾选|基于本次全量跑分自动汇总)）\n\n(?:- \[.\] .*\n)+",
        hypo + "\n",
        text,
        count=1,
    )

    section5 = (
        "## 5. 全量跑分观察\n\n"
        f"本次清空历史后重跑题库全部 {by_group.get('A', {}).get('run_count', '?')} 题 × A/B/C/D 四组（见上表）。\n\n"
        f"- H1（引用质量）：**{mark(h1)}** — {h1_text}\n"
        f"- H2（降质拖累）：**{mark(h2)}** — {h2_detail}\n"
        f"- H3（拒答合理）：**{mark(h3)}** — {h3_text}\n"
        f"- H4（升级RAG）：**{mark(h4)}** — {h4_detail}\n\n"
        "说明：正确性/完整性依赖题库 `reference_points`；拒答合理性在有 `should_abstain` 地面真相时由代码确定性计算。\n\n"
    )
    text = re.sub(
        r"## 5\. (?:初步观察（已有抽样）|全量跑分观察)\n\n.*?(?=\n## 6\.)",
        section5,
        text,
        count=1,
        flags=re.S,
    )

    # 同步第4节标题
    text = re.sub(
        r"## 4\. .*\n\n.*\n\n\| 指标 \|",
        "## 4. 全量跑分结果（含 D 组升级 RAG）\n\n已清空历史记录后，对题库全部题目重跑 A/B/C/D：\n\n| 指标 |",
        text,
        count=1,
    )

    REPORT.write_text(text, encoding="utf-8")
    print(f"[eval] 已回填报告：{REPORT}")


def main():
    reset_runs()
    ok, fail = run_all()
    if ok == 0:
        print("[eval] 没有成功运行的题目，跳过回填")
        sys.exit(1)
    summary = fetch_summary()
    print("\n[eval] 汇总：")
    for row in summary:
        print(row)
    fill_report(summary)
    if fail:
        print(f"[eval] 注意：有 {fail} 题失败，汇总仍基于成功跑完的记录")


if __name__ == "__main__":
    main()
