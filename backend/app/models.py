from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(100), default="")
    # 题目所属测试轨道：事实型 / 机制依据型 / 争议前沿型 / 边界型 / 对抗题-过时观点 / 对抗题-矛盾研究 / 对抗题-缺文献
    track: Mapped[str] = mapped_column(String(50), default="")
    # 期望的证据类型（如"权威指南共识"/"多项RCT一致"/"研究结论存在矛盾"/"知识库无覆盖"），
    # 用于评判时判断系统的证据使用是否得当。
    expected_evidence_type: Mapped[str] = mapped_column(String(200), default="")
    # 出题备注：为什么这题这么设计、期望系统怎么表现（人读的，不进裁判prompt）。
    notes: Mapped[str] = mapped_column(Text, default="")
    # 地面真相：这道题是否"应该"被拒答/坦承证据不足（如边界题、虚构实体的对抗题）。
    # 用于确定性计算"拒答是否合理"，而不是让裁判模型自己猜。
    should_abstain: Mapped[bool] = mapped_column(Boolean, default=False)
    # 评判用的客观参考要点（应从权威指南/文献摘出，用于自动裁判核对"正确性"与"完整性"，
    # 不依赖评分人自身的医学专业知识）。
    reference_points: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    runs: Mapped[list["RunResult"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class RunResult(Base):
    __tablename__ = "run_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    group: Mapped[str] = mapped_column(String(1), nullable=False)  # A / B / C
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_chunks: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    question: Mapped["Question | None"] = relationship(back_populates="runs")
    auto_evaluations: Mapped[list["AutoEvaluation"]] = relationship(
        back_populates="run_result",
        cascade="all, delete-orphan",
        order_by="AutoEvaluation.created_at.desc()",
    )

    @property
    def auto_evaluation(self) -> "AutoEvaluation | None":
        """取最近一次自动评判结果，供序列化用（允许后续重新评判产生多条记录）。"""
        return self.auto_evaluations[0] if self.auto_evaluations else None


class AutoEvaluation(Base):
    """LLM-as-judge 自动评判结果，六个维度都绑定明确的参照物和判断执行者，
    不依赖评分人（无论是团队成员还是终端用户）的主观医学判断。
    """

    __tablename__ = "auto_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_result_id: Mapped[int] = mapped_column(ForeignKey("run_results.id"), nullable=False)

    # 1. 正确性：主结论是否和参考要点/引用原文矛盾
    correctness_verdict: Mapped[str] = mapped_column(String(20), default="unverifiable")
    # consistent / partial / contradicts / unverifiable
    correctness_explanation: Mapped[str] = mapped_column(Text, default="")

    # 2. 完整性：参考要点覆盖率
    completeness_covered: Mapped[list] = mapped_column(JSON, default=list)
    completeness_missed: Mapped[list] = mapped_column(JSON, default=list)
    completeness_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 3. 安全性：是否越界给出具体诊疗指令
    safety_is_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    safety_violations: Mapped[list] = mapped_column(JSON, default=list)

    # 4. 清晰度：目标用户可读性（唯一允许非专业人士参与判断的维度）
    clarity_score: Mapped[float] = mapped_column(Float, default=0)  # 0-5
    clarity_explanation: Mapped[str] = mapped_column(Text, default="")

    # 5. 引用质量：ID合法性（规则校验）+ 内容支撑度（LLM判断）
    invalid_citation_labels: Mapped[list] = mapped_column(JSON, default=list)  # 答案里出现但引用列表里没有的编号
    citation_support: Mapped[list] = mapped_column(JSON, default=list)  # [{label, supported, explanation}]
    citation_support_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 6. 拒答率：是否拒答 + 结合题目地面真相（should_abstain）或检索覆盖度判断是否合理
    is_refusal: Mapped[bool] = mapped_column(Boolean, default=False)
    refusal_appropriate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refusal_explanation: Mapped[str] = mapped_column(Text, default="")
    # 该题预设的"是否应该拒答"地面真相快照（题库题才有，临时提问为 None）。
    # 有该值时，refusal_appropriate 由代码确定性计算（is_refusal == reference_should_abstain），
    # 而不是依赖裁判模型自己猜。
    reference_should_abstain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    avg_retrieval_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_judge_output: Mapped[dict] = mapped_column(JSON, default=dict)
    judge_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run_result: Mapped["RunResult"] = relationship(back_populates="auto_evaluations")
