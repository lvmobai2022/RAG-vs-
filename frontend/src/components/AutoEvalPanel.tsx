import { useState } from "react";
import { api } from "../api/client";
import type { AutoEvaluation } from "../types";

interface Props {
  runId: number;
  evaluation: AutoEvaluation | null;
  onUpdated: (evaluation: AutoEvaluation) => void;
}

const VERDICT_LABEL: Record<string, { text: string; className: string }> = {
  consistent: { text: "一致", className: "verdict-good" },
  partial: { text: "部分一致", className: "verdict-warn" },
  contradicts: { text: "矛盾", className: "verdict-bad" },
  unverifiable: { text: "无法核实（缺参考要点）", className: "verdict-neutral" },
};

export default function AutoEvalPanel({ runId, evaluation, onUpdated }: Props) {
  const [reEvaluating, setReEvaluating] = useState(false);
  const [expanded, setExpanded] = useState(false);

  async function handleReEvaluate() {
    setReEvaluating(true);
    try {
      const updated = await api.reEvaluate(runId);
      if (updated.auto_evaluation) onUpdated(updated.auto_evaluation);
    } catch {
      // 静默失败，用户可以再次点击重试
    } finally {
      setReEvaluating(false);
    }
  }

  if (!evaluation) {
    return (
      <div className="auto-eval-panel auto-eval-empty">
        <span>自动评判结果生成中或失败</span>
        <button type="button" onClick={handleReEvaluate} disabled={reEvaluating}>
          {reEvaluating ? "评判中..." : "重新评判"}
        </button>
      </div>
    );
  }

  const verdict = VERDICT_LABEL[evaluation.correctness_verdict] ?? VERDICT_LABEL.unverifiable;

  return (
    <div className="auto-eval-panel">
      <div className="auto-eval-header">
        <span className="auto-eval-title">LLM-as-judge 自动评判</span>
        <button type="button" className="link-btn" onClick={handleReEvaluate} disabled={reEvaluating}>
          {reEvaluating ? "评判中..." : "重新评判"}
        </button>
      </div>

      {evaluation.judge_error && <div className="error-text">评判出错：{evaluation.judge_error}</div>}

      <div className="auto-eval-grid">
        <div className="auto-eval-item">
          <span className="auto-eval-label">正确性</span>
          <span className={`verdict-badge ${verdict.className}`}>{verdict.text}</span>
        </div>
        <div className="auto-eval-item">
          <span className="auto-eval-label">完整性</span>
          <span>
            {evaluation.completeness_rate !== null ? `${Math.round(evaluation.completeness_rate * 100)}%` : "—"}
          </span>
        </div>
        <div className="auto-eval-item">
          <span className="auto-eval-label">安全性</span>
          <span className={`verdict-badge ${evaluation.safety_is_safe ? "verdict-good" : "verdict-bad"}`}>
            {evaluation.safety_is_safe ? "安全" : `违规 x${evaluation.safety_violations.length}`}
          </span>
        </div>
        <div className="auto-eval-item">
          <span className="auto-eval-label">清晰度</span>
          <span>{evaluation.clarity_score} / 5</span>
        </div>
        <div className="auto-eval-item">
          <span className="auto-eval-label">引用质量</span>
          <span>
            {evaluation.citation_support_rate !== null
              ? `支撑率 ${Math.round(evaluation.citation_support_rate * 100)}%`
              : "无引用"}
            {evaluation.invalid_citation_labels.length > 0 && (
              <span className="flag-bad" style={{ marginLeft: 6 }}>
                编号非法 x{evaluation.invalid_citation_labels.length}
              </span>
            )}
          </span>
        </div>
        <div className="auto-eval-item">
          <span className="auto-eval-label">拒答</span>
          <span>
            {evaluation.is_refusal ? (
              <span className={`verdict-badge ${evaluation.refusal_appropriate ? "verdict-good" : "verdict-warn"}`}>
                是（{evaluation.refusal_appropriate === null ? "存疑" : evaluation.refusal_appropriate ? "合理" : "不合理"}）
              </span>
            ) : (
              "否"
            )}
          </span>
        </div>
      </div>

      {evaluation.reference_should_abstain !== null && (
        <div className={`abstain-check ${evaluation.refusal_appropriate ? "abstain-match" : "abstain-mismatch"}`}>
          题库预期：{evaluation.reference_should_abstain ? "应该拒答" : "不应该拒答"} —— 实际
          {evaluation.is_refusal ? "拒答了" : "没有拒答"}
          {evaluation.refusal_appropriate === false &&
            (evaluation.reference_should_abstain ? "（该拒答但没拒，可能存在编造证据风险）" : "（不该拒答却拒答了，可能过度保守）")}
        </div>
      )}

      <button type="button" className="link-btn" onClick={() => setExpanded((v) => !v)}>
        {expanded ? "收起评判依据" : "查看评判依据"}
      </button>

      {expanded && (
        <div className="auto-eval-detail">
          {evaluation.correctness_explanation && (
            <p>
              <b>正确性依据：</b>
              {evaluation.correctness_explanation}
            </p>
          )}
          {evaluation.completeness_covered.length > 0 && (
            <p>
              <b>已覆盖要点：</b>
              {evaluation.completeness_covered.join("；")}
            </p>
          )}
          {evaluation.completeness_missed.length > 0 && (
            <p>
              <b>未覆盖要点：</b>
              {evaluation.completeness_missed.join("；")}
            </p>
          )}
          {evaluation.safety_violations.length > 0 && (
            <p>
              <b>安全违规点：</b>
              {evaluation.safety_violations.join("；")}
            </p>
          )}
          {evaluation.clarity_explanation && (
            <p>
              <b>清晰度说明：</b>
              {evaluation.clarity_explanation}
            </p>
          )}
          {evaluation.citation_support.length > 0 && (
            <div>
              <b>逐条引用支撑判断：</b>
              <ul>
                {evaluation.citation_support.map((c) => (
                  <li key={c.label}>
                    {c.label} {c.supported ? "✓支撑" : "✗不支撑"} —— {c.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {evaluation.refusal_explanation && (
            <p>
              <b>拒答判断依据：</b>
              {evaluation.refusal_explanation}
            </p>
          )}
          {evaluation.avg_retrieval_distance !== null && (
            <p>
              <b>检索平均向量距离：</b>
              {evaluation.avg_retrieval_distance.toFixed(3)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
