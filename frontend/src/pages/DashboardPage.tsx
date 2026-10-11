import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { GroupSummary } from "../types";
import { GROUP_COLORS } from "../types";

function pct(v: number | null): string {
  return v !== null ? `${Math.round(v * 100)}%` : "—";
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<GroupSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await api.getStatsSummary();
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载统计数据失败");
    } finally {
      setLoading(false);
    }
  }

  const rateData = summary.map((s) => ({
    group: s.label,
    正确性: s.correctness_score !== null ? Math.round(s.correctness_score * 100) : 0,
    完整性: s.completeness_rate !== null ? Math.round(s.completeness_rate * 100) : 0,
    引用支撑率: s.citation_support_rate !== null ? Math.round(s.citation_support_rate * 100) : 0,
    安全违规率: s.safety_violation_rate !== null ? Math.round(s.safety_violation_rate * 100) : 0,
  }));

  const clarityData = summary.map((s) => ({ group: s.label, 清晰度: s.clarity_score ?? 0 }));

  const abstainData = summary.map((s) => ({
    group: s.label,
    应拒答召回率: s.abstain_recall !== null ? Math.round(s.abstain_recall * 100) : 0,
    误拒率: s.over_refusal_rate !== null ? Math.round(s.over_refusal_rate * 100) : 0,
  }));

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <h2>A / B / C 三组对比统计（LLM-as-judge 自动评判）</h2>
        <button type="button" onClick={load} disabled={loading}>
          {loading ? "刷新中..." : "刷新数据"}
        </button>
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="disclaimer-banner">
        以下指标均由自动裁判（LLM-as-judge + 规则脚本）生成，评判依据是每题预设的客观参考要点、检索原文和红线规则，
        不代表已经过真实医生的专业审核；"正确性"仅衡量是否与预设参考要点一致，不等同于医学专业审核结论。
      </div>

      <div className="summary-cards">
        {summary.map((s) => (
          <div key={s.group} className="summary-card" style={{ borderTopColor: GROUP_COLORS[s.group] }}>
            <h4 style={{ color: GROUP_COLORS[s.group] }}>{s.label}</h4>
            <div className="summary-row">运行次数：{s.run_count}（已评判 {s.eval_count}）</div>
            <div className="summary-row">平均耗时：{s.avg_latency_ms} ms</div>
            <div className="summary-row">正确性得分：{s.correctness_score ?? "—"}（矛盾 {s.contradicts_count} 次）</div>
            <div className="summary-row">完整性覆盖率：{pct(s.completeness_rate)}</div>
            <div className="summary-row">清晰度：{s.clarity_score ?? "—"} / 5</div>
            <div className="summary-row">引用支撑率：{pct(s.citation_support_rate)}</div>
            <div className="summary-row">引用编号非法率：{pct(s.invalid_citation_rate)}</div>
            <div className="summary-row">安全违规率：{pct(s.safety_violation_rate)}</div>
            <div className="summary-row">
              拒答次数：{s.refusal_count}（合理率 {pct(s.refusal_appropriate_rate)}）
            </div>
            <div className="summary-row">
              应拒答召回率：{pct(s.abstain_recall)}（{s.abstain_total}题有地面真相）
            </div>
            <div className="summary-row">
              误拒率：{pct(s.over_refusal_rate)}（{s.should_answer_total}题不该拒答）
            </div>
          </div>
        ))}
      </div>

      <div className="chart-block">
        <h3>正确性 / 完整性 / 引用支撑率 / 安全违规率对比（%）</h3>
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={rateData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="group" />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Legend />
            <Bar dataKey="正确性" fill="#2563eb" />
            <Bar dataKey="完整性" fill="#16a34a" />
            <Bar dataKey="引用支撑率" fill="#0891b2" />
            <Bar dataKey="安全违规率" fill="#dc2626" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-block">
        <h3>清晰度对比（0-5分，唯一允许非专业人士参与判断的维度）</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={clarityData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="group" />
            <YAxis domain={[0, 5]} />
            <Tooltip />
            <Bar dataKey="清晰度" fill="#d97706" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-block">
        <h3>应拒答召回率 / 误拒率对比（%，基于题库预设的 should_abstain 地面真相）</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={abstainData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="group" />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Legend />
            <Bar dataKey="应拒答召回率" fill="#16a34a" />
            <Bar dataKey="误拒率" fill="#dc2626" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <p className="dashboard-tip">
        提示：图表数据来自已经跑过自动评判的运行记录（每次在"对比测试"页运行问题都会自动触发评判）。
        正确性/完整性依赖题库里预设的参考要点，没有预设参考要点的题目这两项会显示"无法核实"，不计入相关统计。
      </p>
    </div>
  );
}
