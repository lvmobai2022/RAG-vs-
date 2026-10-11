export interface Question {
  id: number;
  text: string;
  topic: string;
  track: string;
  expected_evidence_type: string;
  notes: string;
  should_abstain: boolean;
  reference_points: string[];
  created_at: string;
}

export interface Citation {
  label: string;
  source_id: string;
  title: string;
  url: string;
  is_noise?: boolean;
}

export interface RefusalGateInfo {
  action: "allow" | "soft_constrain" | "hard_refuse";
  reasons: string[];
  found_summary: string;
  missing_summary: string;
  next_search: string;
  constraints: string[];
}

export interface RetrievedChunk {
  text: string;
  topic: string;
  source: string;
  source_id: string;
  title: string;
  url: string;
  distance: number;
  is_noise: boolean;
  is_gate?: boolean;
  gate?: RefusalGateInfo;
}

export type GroupKey = "A" | "B" | "C" | "D";

export type CorrectnessVerdict = "consistent" | "partial" | "contradicts" | "unverifiable";

export interface CitationSupport {
  label: string;
  supported: boolean;
  explanation: string;
}

export interface AutoEvaluation {
  id: number;
  run_result_id: number;
  correctness_verdict: CorrectnessVerdict;
  correctness_explanation: string;
  completeness_covered: string[];
  completeness_missed: string[];
  completeness_rate: number | null;
  safety_is_safe: boolean;
  safety_violations: string[];
  clarity_score: number;
  clarity_explanation: string;
  invalid_citation_labels: string[];
  citation_support: CitationSupport[];
  citation_support_rate: number | null;
  is_refusal: boolean;
  refusal_appropriate: boolean | null;
  refusal_explanation: string;
  reference_should_abstain: boolean | null;
  avg_retrieval_distance: number | null;
  judge_error: string;
  created_at: string;
}

export interface RunResult {
  id: number;
  question_id: number | null;
  question_text: string;
  group: GroupKey;
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  latency_ms: number;
  created_at: string;
  auto_evaluation: AutoEvaluation | null;
}

export interface GroupSummary {
  group: GroupKey;
  label: string;
  run_count: number;
  eval_count: number;
  avg_latency_ms: number;
  correctness_score: number | null;
  contradicts_count: number;
  completeness_rate: number | null;
  clarity_score: number | null;
  citation_support_rate: number | null;
  safety_violation_rate: number | null;
  invalid_citation_rate: number | null;
  refusal_count: number;
  refusal_rate: number;
  refusal_appropriate_rate: number | null;
  abstain_recall: number | null;
  abstain_total: number;
  over_refusal_rate: number | null;
  should_answer_total: number;
}

export const GROUP_LABELS: Record<GroupKey, string> = {
  A: "A · 纯通用大模型",
  B: "B · RAG（正常检索）",
  C: "C · RAG（降质检索）",
  D: "D · RAG（升级：混合检索+重排）",
};

export const GROUP_COLORS: Record<GroupKey, string> = {
  A: "#6b7280",
  B: "#2563eb",
  C: "#dc2626",
  D: "#059669",
};
