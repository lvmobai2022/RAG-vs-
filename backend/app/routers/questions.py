from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("", response_model=list[schemas.QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    return db.query(models.Question).order_by(models.Question.id).all()


@router.post("", response_model=schemas.QuestionOut)
def create_question(payload: schemas.QuestionCreate, db: Session = Depends(get_db)):
    question = models.Question(
        text=payload.text,
        topic=payload.topic,
        track=payload.track,
        expected_evidence_type=payload.expected_evidence_type,
        notes=payload.notes,
        should_abstain=payload.should_abstain,
        reference_points=payload.reference_points,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.patch("/{question_id}", response_model=schemas.QuestionOut)
def update_question(question_id: int, payload: schemas.QuestionCreate, db: Session = Depends(get_db)):
    question = db.get(models.Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    question.text = payload.text
    question.topic = payload.topic
    question.track = payload.track
    question.expected_evidence_type = payload.expected_evidence_type
    question.notes = payload.notes
    question.should_abstain = payload.should_abstain
    question.reference_points = payload.reference_points
    db.commit()
    db.refresh(question)
    return question


@router.delete("/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    question = db.get(models.Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    db.delete(question)
    db.commit()
    return {"ok": True}
