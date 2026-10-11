from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.judge import run_judge
from app.pipelines.group_a import run_group_a
from app.pipelines.group_b import run_group_b
from app.pipelines.group_c import run_group_c
from app.pipelines.group_d import run_group_d

router = APIRouter(prefix="/api/runs", tags=["runs"])

PIPELINES = {"A": run_group_a, "B": run_group_b, "C": run_group_c, "D": run_group_d}


def _auto_evaluate(
    db: Session,
    run_result: models.RunResult,
    reference_points: list[str],
    should_abstain: bool | None,
) -> None:
    """跑完流水线后自动做 LLM-as-judge 评判，评判者是模型/规则脚本，不是终端用户。"""
    judge_output = run_judge(
        question_text=run_result.question_text,
        group=run_result.group,
        answer_text=run_result.answer,
        citations=run_result.citations,
        retrieved_chunks=run_result.retrieved_chunks,
        reference_points=reference_points,
        should_abstain=should_abstain,
    )
    auto_eval = models.AutoEvaluation(run_result_id=run_result.id, **judge_output)
    db.add(auto_eval)
    db.commit()
    db.refresh(run_result)


@router.post("", response_model=list[schemas.RunResultOut])
def run_comparison(payload: schemas.RunRequest, db: Session = Depends(get_db)):
    question_text = payload.question_text
    topic = None
    expected_evidence_type = ""
    reference_points: list[str] = []
    should_abstain: bool | None = None
    question_id = payload.question_id

    if question_id is not None:
        question = db.get(models.Question, question_id)
        if not question:
            raise HTTPException(status_code=404, detail="问题不存在")
        question_text = question.text
        topic = question.topic or None
        expected_evidence_type = question.expected_evidence_type or ""
        reference_points = question.reference_points or []
        should_abstain = question.should_abstain
    elif not question_text:
        raise HTTPException(status_code=400, detail="必须提供 question_id 或 question_text")

    results = []
    for group in payload.groups:
        pipeline = PIPELINES.get(group)
        if not pipeline:
            continue
        if group == "A":
            output = pipeline(question_text)
        else:
            output = pipeline(
                question_text,
                topic=topic,
                expected_evidence_type=expected_evidence_type,
            )

        run_result = models.RunResult(
            question_id=question_id,
            question_text=question_text,
            group=output["group"],
            answer=output["answer"],
            citations=output["citations"],
            retrieved_chunks=output["retrieved_chunks"],
            latency_ms=output["latency_ms"],
        )
        db.add(run_result)
        db.commit()
        db.refresh(run_result)

        _auto_evaluate(db, run_result, reference_points, should_abstain)
        results.append(run_result)

    return results


@router.get("", response_model=list[schemas.RunResultOut])
def list_runs(question_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.RunResult)
    if question_id is not None:
        query = query.filter(models.RunResult.question_id == question_id)
    return query.order_by(models.RunResult.created_at.desc()).all()


@router.get("/{run_id}", response_model=schemas.RunResultOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run_result = db.get(models.RunResult, run_id)
    if not run_result:
        raise HTTPException(status_code=404, detail="记录不存在")
    return run_result


@router.post("/{run_id}/re-evaluate", response_model=schemas.RunResultOut)
def re_evaluate(run_id: int, db: Session = Depends(get_db)):
    """重新跑一次自动评判（比如调整了参考要点之后）。"""
    run_result = db.get(models.RunResult, run_id)
    if not run_result:
        raise HTTPException(status_code=404, detail="记录不存在")
    question = run_result.question
    reference_points = question.reference_points if question else []
    should_abstain = question.should_abstain if question else None
    _auto_evaluate(db, run_result, reference_points or [], should_abstain)
    return run_result
