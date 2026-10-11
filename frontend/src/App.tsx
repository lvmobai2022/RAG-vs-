import { useState } from "react";
import ComparePage from "./pages/ComparePage";
import DashboardPage from "./pages/DashboardPage";
import "./App.css";

type Tab = "compare" | "dashboard";

function App() {
  const [tab, setTab] = useState<Tab>("compare");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">专用 RAG vs 通用大模型 · 对比评估平台</div>
        <nav className="app-nav">
          <button className={tab === "compare" ? "active" : ""} onClick={() => setTab("compare")}>
            对比测试
          </button>
          <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
            汇总看板
          </button>
        </nav>
      </header>
      <div className="app-body">{tab === "compare" ? <ComparePage /> : <DashboardPage />}</div>
    </div>
  );
}

export default App;
