# 专用 RAG vs 通用大模型 · 对比评估平台

面向"OpenEvidence 风格的证据智能助手"实践项目：**专用 AI vs 通用大模型对比评估**。

不做面向用户的助手，而是搭一个可视化的对比实验平台：对同一批医学/健康问题，同时跑三组流水线并把结果并排展示。评判环节采用 **LLM-as-judge 自动评判**，而不是让项目成员或终端用户凭主观印象打分——每个维度都绑定明确的参照物（预设参考要点 / 检索原文 / 红线规则）和判断执行者（规则脚本或裁判模型）。

## 三组对比设计

| 分组 | 说明 |
| --- | --- |
| **A · 纯通用大模型** | 直接调用大模型回答，不做任何检索增强 |
| **B · RAG（正常检索）** | 纯向量 Top-K 检索 → **拒答阈门** → 拼接 prompt，要求带 `[编号]` 引用 |
| **C · RAG（降质检索）** | 故意混入不相关话题的噪声片段，模拟检索质量差；同样过拒答阈门 |
| **D · RAG（升级）** | **混合检索**（向量 + BM25）→ RRF → 证据加权 → MMR → **重排（默认向量余弦）** → **拒答阈门** |

重排实现见 `backend/app/retrieval/rerank.py`：

| `rerank_backend` | 含义 | 说明 |
| --- | --- | --- |
| `embedding`（**默认**） | 问句–摘要余弦重排 | 复用已有多语言向量模型；本评测下 D 正确性可超过 A |
| `cross-encoder` | `BAAI/bge-reranker-base` | 更细粒度匹配；消融显示正确性/完整性略降、延迟升高 |
| `auto` | 先交叉编码器，失败回退余弦 | 网络不稳时更稳妥 |

### 拒答阈门（B/C/D）

对应课程「合格拒答」要求：用可解释规则决定硬拒答 / 软约束 / 放行，而不是只靠模型自觉。

| 触发 | 行为 |
| --- | --- |
| Top-K 相似度过低、无可用片段、越过诊疗边界（吃药/停药等） | **硬拒答**：跳过生成，返回「已检索到什么 / 缺什么 / 建议补查什么」 |
| 来源 &lt; 3、缺预期证据类型、候选冲突可解释 | **软约束**：仍生成，但注入「禁止下定论 / 并列冲突」等约束 |
| 其余 | 正常生成 |

阈值见 `config.py` 的 `refusal_*`；判定逻辑见 `pipelines/refusal_gate.py`。

这套设计对应课程文档里赛道三的核心问题：RAG 是否减少假引用？是否提高完整性？检索质量差时是否反而拖累回答？专用系统在哪些场景有优势？

## 三条可证伪假设（赛道三要求）

| # | 假设 | 推翻条件 |
| --- | --- | --- |
| H1 | 正常 RAG（B）的引用质量优于裸 LLM（A） | B 无效引用率不低于 A，或引用支撑率不高于 A |
| H2 | 降质检索（C）会拉低完整性/正确性（相对 B） | C 在完整性/正确性上不低于 B |
| H3 | 应拒答题上，带检索系统拒答更合理（召回高、误拒可控） | B/C 在 `should_abstain` 题上大量编造，或在普通题上过度拒答 |

详细判定口径与结果表见 [EVALUATION_REPORT.md](./EVALUATION_REPORT.md)。  
三条 RAG（B/C/D）从设计、拒答阈门、误拒修复到 D 正确性超过 A 的完整思路见 [RAG_DESIGN_NOTES.md](./RAG_DESIGN_NOTES.md)。

## 评判的六个维度和判定标准

评判不依赖评分人自己的医学知识，而是每个维度绑定一个客观参照物，由 LLM 裁判（`app/judge.py`）或规则脚本自动判定：

| 维度 | 参照物 | 判断执行者 |
| --- | --- | --- |
| 正确性 | 题库里预设的 `reference_points`（客观参考要点，来自权威资料） | LLM 裁判做"是否矛盾"文本比对 |
| 完整性 | 同上，统计要点覆盖率 | LLM 裁判逐条判断是否提及 |
| 安全性 | 预定义红线规则（具体用药剂量/明确诊断/劝阻就医） | LLM 裁判做规则分类 |
| 清晰度 | 统一量表锚点 | LLM 裁判（唯一允许非专业人士参与判断的维度） |
| 引用质量 | 引用编号是否在系统提供的列表里（规则）+ 引用原文是否真的支撑结论（LLM 比对） | 规则脚本 + LLM 裁判 |
| 拒答率 | 题库预设的 `should_abstain` 地面真相（有的话），没有则用检索片段平均向量距离兜底 | 有地面真相时代码确定性判定；没有则 LLM 结合检索覆盖度判断 |

每次在"对比测试"页跑一次问题，后端都会自动对 A/B/C 三组结果各跑一次裁判，结果存进 `auto_evaluations` 表，前端只读展示，不需要人工打分。

## 测试集设计

题库（`backend/scripts/seed_questions.py`）覆盖 21 道题（≥15），字段：`track` / `expected_evidence_type` / `notes` / `should_abstain` / `reference_points`。

**非拒答题已按当前知识库覆盖改写**（综述 / Meta / RCT / 实践指南能支撑的问题）；应拒答题仍故意难覆盖。重植命令：`python -m scripts.seed_questions`（会清空旧题与历史 runs）。

| track | 数量 | 说明 |
| --- | --- | --- |
| 事实型 | 4 | 对齐库内难治性高血压、血脂异常、糖尿病指南指标、DOAC vs VKA 等 |
| 机制依据型 | 5 | 地中海饮食、限钠、运动干预等库内有 RCT/meta 的主题 |
| 争议前沿型 | 3 | 现有研究结论本身就不完全一致，测试系统是否诚实呈现不确定性 |
| 边界型 | 3（`should_abstain=True`） | 知识库大概率覆盖不到的细分/前沿问题 |
| 对抗题-过时观点 | 2 | 曾经的主流建议已被更新（如阿司匹林一级预防、低脂饮食），测试系统是否还在重复旧观点 |
| 对抗题-矛盾研究 | 2 | 不同研究结论本身存在分歧（维生素D、红肉与结直肠癌），测试系统是否诚实呈现分歧而不是一刀切结论 |
| 对抗题-缺文献 | 2（`should_abstain=True`） | 涉及虚构药物/技术实体，测试系统是否会为了"凑答案"而编造证据 |

其中 5 道题（边界型 3 + 对抗题-缺文献 2）标注了 `should_abstain=True`，作为"拒答是否合理"评判的地面真相：裁判模块会用 `is_refusal == should_abstain` 来确定性计算这道题的拒答行为是否正确，而不是让裁判模型自己猜。汇总看板上的"应拒答召回率"和"误拒率"就是基于这批地面真相题计算的。

## 知识库与检索式（可复现）

目标有效规模：**≥500** 条摘要（按 PMID/DOI 全局去重后计数）。当前重建后约 **1484** 条（以 `ingest_log.jsonl` 最后一条 `collection_count_after` 为准）。

### 检索策略版本 `v2026-08-11`

组合方式（先窄后宽）：

1. **主题 / 干预词**（英文 query，见 `scripts/ingest.py` 内 `DEFAULT_TOPICS`）
2. **文献类型**：Guideline / Practice Guideline / Review / Systematic Review / Meta-Analysis / Randomized Controlled Trial
3. **出版年**：2016–2026

PubMed 组装示例：

```text
(hypertension antihypertensive medication adherence guideline)
AND ("Guideline"[Publication Type] OR "Practice Guideline"[Publication Type]
  OR "Review"[Publication Type] OR "Systematic Review"[Publication Type]
  OR "Meta-Analysis"[Publication Type]
  OR "Randomized Controlled Trial"[Publication Type])
AND (2016:2026[Date - Publication])
```

Europe PMC 组装示例：

```text
(hypertension antihypertensive medication adherence guideline)
AND (PUB_TYPE:"Review" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta Analysis"
  OR PUB_TYPE:"Guideline" OR PUB_TYPE:"Practice Guideline"
  OR PUB_TYPE:"Randomized Controlled Trial")
AND FIRST_PDATE:[2016-01-01 TO 2026-12-31]
```

### 清洗与元数据

- 跳过空摘要
- 按 `PMID:` / `DOI:` **全局去重**（避免「500 里混重复导致有效规模塌缩」）
- 样例 metadata 字段：`title` / `year` / `source_type` / `source_id` / `url` / `topic`

### 检索日志

每次 ingest 追加写入 `backend/data/ingest_log.jsonl`，字段含：`timestamp`、`topic`、`pubmed_query`、`europepmc_query`、命中数、写入数、写入后总规模。写报告数据章节时直接引用该日志。

重建知识库：

```powershell
.venv\Scripts\python.exe -m scripts.ingest --reset --per-source 40
```

## 项目结构

```
task3/
├── backend/            FastAPI 后端
│   ├── app/
│   │   ├── main.py            应用入口
│   │   ├── config.py          配置（.env）
│   │   ├── models.py          数据库模型（题库/运行结果/自动评判结果）
│   │   ├── judge.py           LLM-as-judge 自动评判模块（六维度）
│   │   ├── llm_client.py      DeepSeek（OpenAI 兼容）客户端
│   │   ├── retrieval/         PubMed / Europe PMC 检索 + Chroma 向量库
│   │   ├── pipelines/         A / B / C 三组流水线
│   │   └── routers/           题库 / 运行 / 统计 API
│   ├── scripts/
│   │   ├── ingest.py          构建知识库（抓取文献写入向量库）
│   │   └── seed_questions.py  预置测试题库（含每题的参考要点）
│   └── requirements.txt
└── frontend/           React + Vite 前端
    └── src/
        ├── pages/ComparePage.tsx     题库 + 临时提问 + 三栏对比
        ├── pages/DashboardPage.tsx   汇总统计看板（六维度图表）
        └── components/               AnswerCard / AutoEvalPanel
```

## 快速开始

### 1. 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 复制配置文件，填入你自己的 DeepSeek API Key
copy .env.example .env
# 编辑 .env，把 DEEPSEEK_API_KEY 换成你自己的 key（https://platform.deepseek.com 申请）

# 预置一批测试问题（高血压/血脂/糖尿病/饮食干预，覆盖事实型/机制依据型/争议前沿型/边界型）
.venv\Scripts\python.exe scripts\seed_questions.py

# 构建知识库：从 PubMed + Europe PMC 抓取文献摘要写入本地向量库（首次运行会下载一个多语言 embedding 模型，约几百MB）
.venv\Scripts\python.exe -m scripts.ingest

# 启动后端服务
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

后端默认监听 `http://127.0.0.1:8000`，可以访问 `http://127.0.0.1:8000/docs` 看自动生成的 API 文档。

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`，如果后端不在默认地址，可以在 `frontend/.env` 里设置：

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 使用流程

1. **对比测试页**：左侧是题库（预置了 21 道分层测试题，含应拒答/对抗题），点"运行 A/B/C 对比"会同时触发三条流水线并自动跑完评判，右侧以三栏卡片展示各组回答、引用来源、耗时，并可展开查看检索到的原始片段（降质组会标出"噪声片段"）。也可以在下方输入临时问题（无参考要点，正确性/完整性会显示"无法核实"）。新增题目时可填轨道、`should_abstain` 与参考要点。
2. **自动评判结果**：每张回答卡片下面是只读的 `AutoEvalPanel`，展示六个维度的判定结果，点"查看评判依据"能看到裁判给出的具体理由。如果调整了题目的参考要点，可以点"重新评判"重跑裁判。
3. **汇总看板**：切到"汇总看板"页签，看三组在六个维度上的对比图表和统计卡片（含应拒答召回率/误拒率），用于最终汇报展示。
4. **评估报告**：填写 [EVALUATION_REPORT.md](./EVALUATION_REPORT.md) 中的结果表与假设判定，作为第 3 天交付物之一。

## 扩充知识库

`scripts/ingest.py` 默认覆盖 12 个话题（高血压/血脂/糖尿病/地中海饮食/限钠/抗凝/心血管预防/维生素D/饮食与癌症/运动/低碳水/低脂），每话题可有多条 query：

```powershell
.venv\Scripts\python.exe -m scripts.ingest --topic "运动干预" --query "exercise intervention type 2 diabetes glycemic control"
```

或者写一个 JSON 配置批量导入：

```powershell
.venv\Scripts\python.exe -m scripts.ingest --config scripts\topics.json
```

## 关于"降质检索"（C组）的实现说明

`degraded_noise_ratio`（默认 0.6，可在 `.env` 调整）控制 C 组检索结果里噪声片段的比例：会用其它不相关话题的文献片段替换掉一部分本应命中的相关片段，前端会用红色"噪声片段"标签标出，方便评分时核对模型是否真的被带偏、有没有把噪声片段当真去回答。

## 后续可以补充的方向（进阶）

- 已完成：混合检索 + 证据加权 + MMR + 重排（第 D 组；默认余弦，交叉编码器已消融）
- 引用 ID 反查真实性：再加一层反查 PMID/DOI 是否真实存在
- Tool / MCP：把 PubMed 检索与引用校验做成可调用工具
- LLM Wiki 主题页作为非纯向量知识库路线
- 引入 Ragas / TruLens 与自建裁判交叉验证
- 按参考要点做知识库缺口表，冲击完整性 D>A
