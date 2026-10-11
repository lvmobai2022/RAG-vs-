from datetime import datetime

from pydantic import BaseModel


class QuestionCreate(BaseModel):
    text: str
    topic: str = ""
    track: str = ""
    expected_evidence_type: str = ""
    notes: str = ""
    should_abstain: bool = False
    reference_points: list[str] = []


class QuestionOut(BaseModel):
    id: int
    text: str
    topic: str
    track: str
    expected_evidence_type: str
    notes: str
    should_abstain: bool
    reference_points: list[str]
    created_at: datetime

    class Config:
        from_attributes = True


class Citation(BaseModel):
    label: str  # 如 [1]
    source_id: str  # PMID / DOI / NCTxxxx
    title: str
    url: str = ""


class RunRequest(BaseModel):
    question_id: int | None = None
    question_text: str | None = None
    groups: list[str] = ["A", "B", "C", "D"]


class AutoEvaluationOut(BaseModel):
    id: int
    run_result_id: int
    correctness_verdict: str
    correctness_explanation: str
    completeness_covered: list[str]
    completeness_missed: list[str]
    completeness_rate: float | None
    safety_is_safe: bool
    safety_violations: list[str]
    clarity_score: float
    clarity_explanation: str
    invalid_citation_labels: list[str]
    citation_support: list[dict]
    citation_support_rate: float | None
    is_refusal: bool
    refusal_appropriate: bool | None
    refusal_explanation: str
    reference_should_abstain: bool | None
    avg_retrieval_distance: float | None
    judge_error: str
    created_at: datetime

    class Config:
        from_attributes = True


class RunResultOut(BaseModel):
    id: int
    question_id: int | None
    question_text: str
    group: str
    answer: str
    citations: list[dict]
    retrieved_chunks: list[dict]
    latency_ms: int
    created_at: datetime
    auto_evaluation: AutoEvaluationOut | None = None

    class Config:
        from_attributes = True
