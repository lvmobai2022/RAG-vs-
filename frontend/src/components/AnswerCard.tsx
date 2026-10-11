import { useState } from "react";
import AutoEvalPanel from "./AutoEvalPanel";
import type { AutoEvaluation, RefusalGateInfo, RunResult } from "../types";
import { GROUP_COLORS, GROUP_LABELS } from "../types";

interface Props {
  result: RunResult;
}

function extractGate(result: RunResult): RefusalGateInfo | null {
  const gateChunk = result.retrieved_chunks.find((c) => c.is_gate && c.gate);
  return gateChunk?.gate ?? null;
}

const GATE_ACTION_LABEL: Record<RefusalGateInfo["action"], string> = {
  allow: "放行",
  soft_constrain: "软约束",
  hard_refuse: "硬拒答",
};

export default function AnswerCard({ result }: Props) {
  const [evaluation, setEvaluation] = useState<AutoEvaluation | null>(result.auto_evaluation);
  const [showChunks, setShowChunks] = useState(false);

  const color = GROUP_COLORS[result.group];
  const gate = extractGate(result);
  const evidenceChunks = result.retrieved_chunks.filter((c) => !c.is_gate);

  return (
    <div className="answer-card" style={{ borderTopColor: color }}>
      <div className="answer-card-header" style={{ color }}>
        <span>{GROUP_LABELS[result.group]}</span>
        <span className="latency">{result.latency_ms} ms</span>
      </div>

      {gate && gate.action !== "allow" && (
        <div className={`gate-panel gate-${gate.action}`}>
          <div className="gate-title">
            拒答阈门：{GATE_ACTION_LABEL[gate.action]}
          </div>
          <ul className="gate-reasons">
            {gate.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {gate.action === "hard_refuse" && (
            <div className="gate-detail">
              <div>已检索：{gate.found_summary}</div>
              <div>缺失：{gate.missing_summary}</div>
              <div>建议：{gate.next_search}</div>
            </div>
          )}
          {gate.action === "soft_constrain" && gate.constraints.length > 0 && (
            <div className="gate-detail">
              约束：{gate.constraints.join("；")}
            </div>
          )}
        </div>
      )}

      <div className="answer-text">{result.answer}</div>

      {result.citations.length > 0 && (
        <div className="citations">
          <div className="citations-title">引用来源（{result.citations.length}）</div>
          <ul>
            {result.citations.map((c) => (
              <li key={c.label} className={c.is_noise ? "citation-noise" : ""}>
                <span className="citation-label">{c.label}</span>
                {c.url ? (
                  <a href={c.url} target="_blank" rel="noreferrer">
                    {c.title}
                  </a>
                ) : (
                  <span>{c.title}</span>
                )}
                <span className="citation-source-id">{c.source_id}</span>
                {c.is_noise && <span className="noise-badge">噪声片段</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {evidenceChunks.length > 0 && (
        <div className="chunks-toggle">
          <button type="button" onClick={() => setShowChunks((v) => !v)}>
            {showChunks ? "收起检索原文" : "查看检索原文"}
          </button>
          {showChunks && (
            <div className="chunks-list">
              {evidenceChunks.map((chunk, idx) => (
                <div key={idx} className={`chunk-item ${chunk.is_noise ? "chunk-noise" : ""}`}>
                  <div className="chunk-meta">
                    [{idx + 1}] {chunk.title} {chunk.is_noise && <span className="noise-badge">噪声</span>}
                  </div>
                  <div className="chunk-text">{chunk.text.slice(0, 300)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="evaluation-section">
        <AutoEvalPanel runId={result.id} evaluation={evaluation} onUpdated={setEvaluation} />
      </div>
    </div>
  );
}
