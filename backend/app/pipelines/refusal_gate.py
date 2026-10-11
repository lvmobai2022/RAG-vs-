"""拒答阈门：用可解释规则决定「硬拒答 / 软约束 / 正常生成」。

对应课程 PPT：
- 四种情况必须触发拒答（相似度过低 / 未命中证据类型 / 无法解释的冲突 / 越过诊疗边界）
- 合格拒答 = 已检索到什么 + 缺什么 + 建议补查什么
- 四条可解释阈值：来源<3 不下定论；缺预期证据类型标不足；冲突并列；问吃药/停药安全拒答
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import settings

# 诊疗边界：具体用药/停药决策（不是科普机制）
_MEDICATION_BOUNDARY = re.compile(
    r"(吃什么药|开什么药|停药|该不该停|怎么停药|用药剂量|吃多少|一天几次|"
    r"处方|给我开药|替我诊断|是不是得了|确诊|治疗方案怎么定|能不能停药)",
    re.I,
)

_EVIDENCE_KEYWORDS = {
    "guideline": ["guideline", "practice guideline", "指南", "权威指南", "共识"],
    "rct": ["randomized controlled trial", "clinical trial", "rct", "随机对照", "随机试验"],
    "review": ["systematic review", "meta-analysis", "meta analysis", "系统综述", "荟萃"],
    "conflict": ["矛盾", "不一致", "争议", "不完全一致"],
    "uncovered": ["知识库无覆盖", "无覆盖", "虚构"],
}


@dataclass
class GateResult:
    action: str  # allow | soft_constrain | hard_refuse
    reasons: list[str] = field(default_factory=list)
    found_summary: str = ""
    missing_summary: str = ""
    next_search: str = ""
    constraints: list[str] = field(default_factory=list)  # soft 时注入 prompt

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reasons": self.reasons,
            "found_summary": self.found_summary,
            "missing_summary": self.missing_summary,
            "next_search": self.next_search,
            "constraints": self.constraints,
        }


def _non_noise_chunks(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if not c.get("is_noise")]


def _avg_distance(chunks: list[dict]) -> float | None:
    dists = [c.get("distance") for c in chunks if isinstance(c.get("distance"), (int, float))]
    dists = [d for d in dists if d < 900]  # 过滤 BM25-only 占位大距离
    if not dists:
        return None
    return sum(dists) / len(dists)


def _min_distance(chunks: list[dict]) -> float | None:
    dists = [c.get("distance") for c in chunks if isinstance(c.get("distance"), (int, float))]
    dists = [d for d in dists if d < 900]
    if not dists:
        return None
    return min(dists)


def _source_types_blob(chunks: list[dict]) -> str:
    return " ".join(str(c.get("source_type", "")).lower() for c in chunks)


def _titles_blob(chunks: list[dict]) -> str:
    return "；".join(str(c.get("title", ""))[:80] for c in chunks[:5] if c.get("title"))


def _expected_buckets(expected_evidence_type: str) -> set[str]:
    text = (expected_evidence_type or "").lower()
    buckets: set[str] = set()
    if any(k in text for k in _EVIDENCE_KEYWORDS["guideline"]):
        buckets.add("guideline")
    if any(k in text for k in ["rct", "随机", "试验", "多项rct"]):
        buckets.add("rct")
    if any(k in text for k in ["系统综述", "meta", "荟萃", "综述"]):
        buckets.add("review")
    if any(k in text for k in _EVIDENCE_KEYWORDS["conflict"]):
        buckets.add("conflict_ok")
    if any(k in text for k in _EVIDENCE_KEYWORDS["uncovered"]):
        buckets.add("uncovered")
    return buckets


def _hit_buckets(chunks: list[dict]) -> set[str]:
    blob = (
        _source_types_blob(chunks)
        + " "
        + " ".join(f"{c.get('title', '')} {c.get('text', '')[:120]}" for c in chunks).lower()
    )
    hits: set[str] = set()
    if any(k in blob for k in ["guideline", "practice guideline", "consensus", "指南", "共识"]):
        hits.add("guideline")
    if any(k in blob for k in ["randomized controlled trial", "clinical trial", "随机对照"]):
        hits.add("rct")
    if any(
        k in blob
        for k in ["systematic review", "meta-analysis", "meta analysis", "系统综述", "荟萃", "review"]
    ):
        hits.add("review")
    return hits


def _looks_conflicted(chunks: list[dict], question: str) -> bool:
    """粗粒度冲突检测：标题/摘要里同时出现相反极性词，或题目本身要求呈现争议。"""
    text = " ".join(f"{c.get('title','')} {c.get('text','')[:200]}" for c in chunks).lower()
    pos = sum(1 for w in ["benefit", "effective", "获益", "有效", "降低风险", "推荐"] if w in text)
    neg = sum(1 for w in ["no benefit", "ineffective", "无效", "无获益", "不推荐", "harm", "风险增加"] if w in text)
    q = question.lower()
    asks_conflict = any(k in q for k in ["争议", "一致吗", "是否一致", "有没有争议", "结论一致"])
    return (pos >= 2 and neg >= 2) or asks_conflict


def evaluate_refusal_gate(
    question: str,
    chunks: list[dict],
    *,
    expected_evidence_type: str = "",
) -> GateResult:
    usable = _non_noise_chunks(chunks)
    avg_dist = _avg_distance(usable)
    min_dist = _min_distance(usable)
    titles = _titles_blob(usable)
    expected = _expected_buckets(expected_evidence_type)
    hits = _hit_buckets(usable)

    reasons: list[str] = []
    constraints: list[str] = []
    missing_parts: list[str] = []
    next_parts: list[str] = []
    hard = False

    found = (
        f"检索到 {len(usable)} 条可用片段"
        + (f"（平均向量距离 {avg_dist:.3f}）" if avg_dist is not None else "")
        + (f"：{titles}" if titles else "。")
    )

    # 1) Top-K 相似度过低
    max_avg = settings.refusal_max_avg_distance
    max_best = settings.refusal_max_best_distance
    if not usable:
        hard = True
        reasons.append("未检索到任何可用资料")
        missing_parts.append("相关文献摘要")
        next_parts.append("扩大主题词并补充 Guideline/RCT 检索式")
    elif min_dist is not None and min_dist > max_best:
        hard = True
        reasons.append(f"Top-K 最佳相似度过低（最小距离 {min_dist:.3f} > {max_best}）")
        missing_parts.append("与问题高相关的证据片段")
        next_parts.append("换用更精确的 MeSH/干预词，或放宽年份后再检索")
    elif avg_dist is not None and avg_dist > max_avg:
        hard = True
        reasons.append(f"Top-K 平均相似度过低（平均距离 {avg_dist:.3f} > {max_avg}）")
        missing_parts.append("稳定相关的证据簇")
        next_parts.append("检查知识库是否覆盖该细分问题")

    # 2) 未命中所需证据类型（预期明确且不是「无覆盖/争议」时）
    needed = expected - {"conflict_ok", "uncovered"}
    if needed and usable:
        miss = needed - hits
        if miss:
            label = "、".join(sorted(miss))
            missing_parts.append(f"预期证据类型：{label}")
            next_parts.append(f"定向补查 {label} 类文献（Guideline/RCT/Systematic Review）")
            if "uncovered" in expected or hard:
                hard = True
                reasons.append(f"未命中所需证据类型（缺 {label}）")
            elif min_dist is not None and min_dist <= max_best:
                # 相似度尚可：只在面板上提示类型缺口，不注入会诱发拒答开场的软约束
                reasons.append(f"证据类型标注不足（缺 {label}），仍允许基于已检索资料作答")
            else:
                reasons.append(f"证据类型不足（缺 {label}），需标注不确定")
                constraints.append(
                    "证据相关性偏弱且缺少预期类型：先尽可能概述已有资料，并明确说明缺口；"
                    "仅当资料与问题明显无关时才可拒答；禁止空泛拒答开场"
                )

    # 预期就是知识库无覆盖：相关度差时硬拒
    if "uncovered" in expected and usable and min_dist is not None and min_dist > settings.refusal_max_best_distance * 0.85:
        hard = True
        if "预期为知识库难覆盖问题" not in reasons:
            reasons.append("预期为知识库难覆盖问题，且检索相关性不足")
        missing_parts.append("可直接支撑结论的高质量证据")
        next_parts.append("人工核对是否存在真实 PMID/指南；避免编造")

    # 3) 冲突：可解释则软约束并列；若同时还极不相关则硬拒
    conflicted = _looks_conflicted(usable, question)
    if conflicted and usable:
        if avg_dist is not None and avg_dist > max_avg:
            hard = True
            reasons.append("候选证据相互冲突且整体相关性过低，无法可靠解释")
        else:
            reasons.append("候选证据可能存在冲突/争议")
            constraints.append("若资料结论不一致，必须并列呈现双方，禁止只挑一边下定论")

    # 4) 越过诊疗边界
    if _MEDICATION_BOUNDARY.search(question or ""):
        hard = True
        reasons.append("问题越过诊疗边界（涉及具体用药/停药/诊断决策）")
        missing_parts.append("个体化临床评估信息（病史、检验、禁忌症等）")
        next_parts.append("建议由执业医师面诊决策；本系统仅可提供公开科普级机制说明（若有证据）")

    # 规则：来源 < 3 -> 标明证据有限（软）；降质组混入噪声后可用片段变少，不能因此逼成拒答
    has_noise = any(c.get("is_noise") for c in chunks)
    if 0 < len(usable) < settings.refusal_min_sources and not has_noise:
        reasons.append(f"可用来源少于 {settings.refusal_min_sources} 个")
        constraints.append(
            f"可用来源仅 {len(usable)} 个：请基于现有资料作答并标明证据有限，"
            "禁止以拒答开场；不要编造未检索到的细节"
        )
        if not next_parts:
            next_parts.append("补充至少 3 条独立来源后再尝试更完整回答")
    elif has_noise and len(usable) < settings.refusal_min_sources:
        reasons.append("降质检索导致可用非噪声来源偏少（实验设定，不因此硬拒）")
        constraints.append(
            "检索结果含噪声片段：请优先依据非噪声资料作答，忽略明显不相关噪声；"
            "禁止因噪声而拒答整道题"
        )

    if hard:
        action = "hard_refuse"
    elif constraints:
        action = "soft_constrain"
    else:
        action = "allow"

    return GateResult(
        action=action,
        reasons=reasons,
        found_summary=found,
        missing_summary="；".join(dict.fromkeys(missing_parts)) or "（未额外标记缺失项）",
        next_search="；".join(dict.fromkeys(next_parts)) or "（可维持当前检索策略）",
        constraints=constraints,
    )


def build_qualified_refusal(question: str, gate: GateResult) -> str:
    """合格拒答 = 已检索到什么 + 缺什么 + 建议补查什么（不等于只说「我不能回答」）。"""
    lines = [
        "现有资料不足以支持对这个问题给出确定结论（系统触发拒答阈门）。",
        "",
        f"【已检索到什么】{gate.found_summary}",
        f"【缺什么】{gate.missing_summary}",
        f"【建议下一步查什么】{gate.next_search}",
        "",
        "触发原因：",
    ]
    for r in gate.reasons:
        lines.append(f"- {r}")
    lines.extend(
        [
            "",
            "说明：不知道时承认不知道，比把低相关内容组织成答案更可靠。"
            "本系统仅供教学演示，不提供诊疗建议。",
        ]
    )
    return "\n".join(lines)


def apply_soft_constraints_to_prompt(user_prompt: str, gate: GateResult) -> str:
    if not gate.constraints:
        return user_prompt
    extra = ["", "【拒答阈门-软约束，必须遵守】"]
    for c in gate.constraints:
        extra.append(f"- {c}")
    extra.append("若约束与资料冲突，优先遵守约束并说明证据边界。")
    return user_prompt + "\n".join(extra)


def gate_chunk(gate: GateResult) -> dict:
    """写入 retrieved_chunks，方便前端展示阈门判定。"""
    return {
        "text": (
            f"action={gate.action}\n"
            f"reasons={'; '.join(gate.reasons)}\n"
            f"found={gate.found_summary}\n"
            f"missing={gate.missing_summary}\n"
            f"next={gate.next_search}"
        ),
        "topic": "",
        "source": "refusal_gate",
        "source_id": "GATE",
        "title": "拒答阈门判定",
        "url": "",
        "distance": 0.0,
        "is_noise": False,
        "is_gate": True,
        "gate": gate.to_dict(),
    }
