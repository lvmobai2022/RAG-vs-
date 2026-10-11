from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api/stats", tags=["stats"])

GROUPS = ["A", "B", "C", "D"]
GROUP_LABELS = {
    "A": "纯通用大模型",
    "B": "RAG（正常检索）",
    "C": "RAG（降质检索）",
    "D": "RAG（升级：混合检索）",
}


def _latest_eval_ids_subquery(db: Session):
    """每个 run_result 可能被重新评判多次，统计只取每条运行记录最新一次评判结果。"""
    return (
        db.query(func.max(models.AutoEvaluation.id))
        .group_by(models.AutoEvaluation.run_result_id)
        .subquery()
    )


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    latest_ids = _latest_eval_ids_subquery(db)
    summary = []
    for group in GROUPS:
        base_query = (
            db.query(models.AutoEvaluation)
            .join(models.RunResult, models.AutoEvaluation.run_result_id == models.RunResult.id)
            .filter(models.RunResult.group == group)
            .filter(models.AutoEvaluation.id.in_(latest_ids))
        )

        run_count = db.query(func.count(models.RunResult.id)).filter(models.RunResult.group == group).scalar() or 0
        avg_latency = (
            db.query(func.avg(models.RunResult.latency_ms)).filter(models.RunResult.group == group).scalar() or 0
        )

        eval_count = base_query.count()

        # 正确性：consistent=1 partial=0.5 contradicts=0，unverifiable 不计入分母
        correctness_score = func.avg(
            case(
                (models.AutoEvaluation.correctness_verdict == "consistent", 1.0),
                (models.AutoEvaluation.correctness_verdict == "partial", 0.5),
                (models.AutoEvaluation.correctness_verdict == "contradicts", 0.0),
                else_=None,
            )
        )
        contradicts_count = base_query.filter(models.AutoEvaluation.correctness_verdict == "contradicts").count()

        avg_completeness = base_query.with_entities(func.avg(models.AutoEvaluation.completeness_rate)).scalar()
        avg_clarity = base_query.with_entities(func.avg(models.AutoEvaluation.clarity_score)).scalar()
        avg_citation_support = base_query.with_entities(func.avg(models.AutoEvaluation.citation_support_rate)).scalar()

        safety_violation_rate = base_query.with_entities(
            func.avg(case((models.AutoEvaluation.safety_is_safe.is_(False), 1.0), else_=0.0))
        ).scalar()

        invalid_citation_rate = base_query.with_entities(
            func.avg(
                case(
                    (func.json_array_length(models.AutoEvaluation.invalid_citation_labels) > 0, 1.0),
                    else_=0.0,
                )
            )
        ).scalar()

        refusal_count = base_query.filter(models.AutoEvaluation.is_refusal.is_(True)).count()
        refusal_appropriate_count = base_query.filter(
            models.AutoEvaluation.is_refusal.is_(True), models.AutoEvaluation.refusal_appropriate.is_(True)
        ).count()

        # 应拒答召回率：题库里标注"应该拒答"的题，模型实际拒答的比例（只统计有地面真相的题）
        should_abstain_total = base_query.filter(models.AutoEvaluation.reference_should_abstain.is_(True)).count()
        should_abstain_refused = base_query.filter(
            models.AutoEvaluation.reference_should_abstain.is_(True), models.AutoEvaluation.is_refusal.is_(True)
        ).count()

        # 误拒率：题库里标注"不该拒答"的题，模型却拒答的比例
        should_answer_total = base_query.filter(models.AutoEvaluation.reference_should_abstain.is_(False)).count()
        should_answer_but_refused = base_query.filter(
            models.AutoEvaluation.reference_should_abstain.is_(False), models.AutoEvaluation.is_refusal.is_(True)
        ).count()

        correctness_avg = base_query.with_entities(correctness_score).scalar()

        summary.append(
            {
                "group": group,
                "label": GROUP_LABELS[group],
                "run_count": run_count,
                "eval_count": eval_count,
                "avg_latency_ms": round(avg_latency, 1),
                "correctness_score": round(correctness_avg, 3) if correctness_avg is not None else None,
                "contradicts_count": contradicts_count,
                "completeness_rate": round(avg_completeness, 3) if avg_completeness is not None else None,
                "clarity_score": round(avg_clarity, 2) if avg_clarity is not None else None,
                "citation_support_rate": round(avg_citation_support, 3) if avg_citation_support is not None else None,
                "safety_violation_rate": round(safety_violation_rate, 3) if safety_violation_rate is not None else None,
                "invalid_citation_rate": round(invalid_citation_rate, 3) if invalid_citation_rate is not None else None,
                "refusal_count": refusal_count,
                "refusal_rate": round(refusal_count / eval_count, 3) if eval_count else 0,
                "refusal_appropriate_rate": (
                    round(refusal_appropriate_count / refusal_count, 3) if refusal_count else None
                ),
                "abstain_recall": (
                    round(should_abstain_refused / should_abstain_total, 3) if should_abstain_total else None
                ),
                "abstain_total": should_abstain_total,
                "over_refusal_rate": (
                    round(should_answer_but_refused / should_answer_total, 3) if should_answer_total else None
                ),
                "should_answer_total": should_answer_total,
            }
        )
    return summary
