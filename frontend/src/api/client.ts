import type { GroupKey, GroupSummary, Question, RunResult } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`请求失败 ${resp.status}: ${detail}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  listQuestions: () => request<Question[]>("/api/questions"),

  createQuestion: (payload: {
    text: string;
    topic?: string;
    track?: string;
    expected_evidence_type?: string;
    notes?: string;
    should_abstain?: boolean;
    reference_points?: string[];
  }) => request<Question>("/api/questions", { method: "POST", body: JSON.stringify(payload) }),

  deleteQuestion: (id: number) => request<{ ok: boolean }>(`/api/questions/${id}`, { method: "DELETE" }),

  runComparison: (payload: { question_id?: number; question_text?: string; groups?: GroupKey[] }) =>
    request<RunResult[]>("/api/runs", { method: "POST", body: JSON.stringify(payload) }),

  listRuns: (questionId?: number) =>
    request<RunResult[]>(`/api/runs${questionId ? `?question_id=${questionId}` : ""}`),

  reEvaluate: (runId: number) => request<RunResult>(`/api/runs/${runId}/re-evaluate`, { method: "POST" }),

  getStatsSummary: () => request<GroupSummary[]>("/api/stats/summary"),
};
