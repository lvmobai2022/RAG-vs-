import { useEffect, useState } from "react";
import { api } from "../api/client";
import AnswerCard from "../components/AnswerCard";
import type { GroupKey, Question, RunResult } from "../types";

const ALL_GROUPS: GroupKey[] = ["A", "B", "C", "D"];

export default function ComparePage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [results, setResults] = useState<RunResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const [adHocText, setAdHocText] = useState("");

  const [newText, setNewText] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [newTrack, setNewTrack] = useState("");
  const [newExpectedEvidenceType, setNewExpectedEvidenceType] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [newShouldAbstain, setNewShouldAbstain] = useState(false);
  const [newReferencePoints, setNewReferencePoints] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    refreshQuestions();
  }, []);

  async function refreshQuestions() {
    try {
      const list = await api.listQuestions();
      setQuestions(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载题库失败");
    }
  }

  async function loadLatestRunsForQuestion(questionId: number) {
    try {
      const runs = await api.listRuns(questionId);
      const latestByGroup = new Map<GroupKey, RunResult>();
      for (const run of runs) {
        if (!latestByGroup.has(run.group)) {
          latestByGroup.set(run.group, run);
        }
      }
      setResults(ALL_GROUPS.map((g) => latestByGroup.get(g)).filter(Boolean) as RunResult[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载历史结果失败");
    }
  }

  async function handleSelectQuestion(q: Question) {
    setSelectedId(q.id);
    setError("");
    await loadLatestRunsForQuestion(q.id);
  }

  async function handleRun(questionId: number) {
    setRunning(true);
    setError("");
    try {
      const res = await api.runComparison({ question_id: questionId, groups: ALL_GROUPS });
      setSelectedId(questionId);
      setResults(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行失败，请检查后端服务和 API Key 是否配置正确");
    } finally {
      setRunning(false);
    }
  }

  async function handleRunAdHoc() {
    if (!adHocText.trim()) return;
    setRunning(true);
    setError("");
    setSelectedId(null);
    try {
      const res = await api.runComparison({ question_text: adHocText.trim(), groups: ALL_GROUPS });
      setResults(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行失败，请检查后端服务和 API Key 是否配置正确");
    } finally {
      setRunning(false);
    }
  }

  async function handleAddQuestion() {
    if (!newText.trim()) return;
    const referencePoints = newReferencePoints
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await api.createQuestion({
        text: newText.trim(),
        topic: newTopic.trim(),
        track: newTrack.trim(),
        expected_evidence_type: newExpectedEvidenceType.trim(),
        notes: newNotes.trim(),
        should_abstain: newShouldAbstain,
        reference_points: referencePoints,
      });
      setNewText("");
      setNewTopic("");
      setNewTrack("");
      setNewExpectedEvidenceType("");
      setNewNotes("");
      setNewShouldAbstain(false);
      setNewReferencePoints("");
      setShowAddForm(false);
      await refreshQuestions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加问题失败");
    }
  }

  async function handleDeleteQuestion(id: number) {
    try {
      await api.deleteQuestion(id);
      if (selectedId === id) {
        setSelectedId(null);
        setResults([]);
      }
      await refreshQuestions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  return (
    <div className="compare-page">
      <aside className="question-panel">
        <div className="panel-header">
          <h3>测试题库（{questions.length}）</h3>
          <button type="button" onClick={() => setShowAddForm((v) => !v)}>
            {showAddForm ? "取消" : "+ 新增问题"}
          </button>
        </div>

        {showAddForm && (
          <div className="add-question-form">
            <textarea placeholder="问题内容" value={newText} onChange={(e) => setNewText(e.target.value)} rows={2} />
            <input placeholder="话题（如：高血压）" value={newTopic} onChange={(e) => setNewTopic(e.target.value)} />
            <input
              placeholder="测试轨道（如：事实型/机制依据型/争议前沿型/边界型/对抗题-过时观点）"
              value={newTrack}
              onChange={(e) => setNewTrack(e.target.value)}
            />
            <input
              placeholder="期望的证据类型（如：权威指南共识/研究结论存在矛盾/知识库无覆盖）"
              value={newExpectedEvidenceType}
              onChange={(e) => setNewExpectedEvidenceType(e.target.value)}
            />
            <textarea
              placeholder="出题备注（为什么这么设计这道题，选填）"
              value={newNotes}
              onChange={(e) => setNewNotes(e.target.value)}
              rows={2}
            />
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={newShouldAbstain}
                onChange={(e) => setNewShouldAbstain(e.target.checked)}
              />
              这道题预期系统应该拒答/坦承证据不足（边界题、虚构实体等）
            </label>
            <textarea
              placeholder="客观参考要点，一行一条（用于自动评判正确性/完整性，建议摘自权威指南或文献）"
              value={newReferencePoints}
              onChange={(e) => setNewReferencePoints(e.target.value)}
              rows={3}
            />
            <button type="button" onClick={handleAddQuestion}>保存问题</button>
          </div>
        )}

        <ul className="question-list">
          {questions.map((q) => (
            <li key={q.id} className={q.id === selectedId ? "selected" : ""}>
              <div className="question-text" onClick={() => handleSelectQuestion(q)}>
                {q.text}
              </div>
              <div className="question-meta">
                <span>{q.topic}</span>
                <span>{q.track}</span>
                <span>{(q.reference_points?.length ?? 0) > 0 ? `参考要点x${q.reference_points.length}` : "无参考要点"}</span>
                {q.should_abstain && <span className="abstain-badge">预期拒答</span>}
              </div>
              <div className="question-actions">
                <button type="button" disabled={running} onClick={() => handleRun(q.id)}>
                  {running && selectedId === q.id ? "运行中..." : "运行 A/B/C/D 对比"}
                </button>
                <button type="button" className="link-btn danger" onClick={() => handleDeleteQuestion(q.id)}>
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>

        <div className="adhoc-panel">
          <h3>临时提问（不入题库）</h3>
          <textarea
            placeholder="直接输入一个问题，现场跑四组对比"
            value={adHocText}
            onChange={(e) => setAdHocText(e.target.value)}
            rows={2}
          />
          <button type="button" disabled={running} onClick={handleRunAdHoc}>
            {running ? "运行中..." : "运行临时对比"}
          </button>
        </div>
      </aside>

      <main className="results-panel">
        {error && <div className="error-banner">{error}</div>}
        {results.length === 0 && !running && (
          <div className="empty-hint">从左侧选择一个问题运行对比，或直接输入临时问题测试。</div>
        )}
        {running && results.length === 0 && <div className="empty-hint">四组流水线正在运行，请稍候（涉及检索 + LLM 生成，可能需要一两分钟）...</div>}
        <div className="answer-grid">
          {results.map((r) => (
            <AnswerCard key={r.id} result={r} />
          ))}
        </div>
      </main>
    </div>
  );
}
