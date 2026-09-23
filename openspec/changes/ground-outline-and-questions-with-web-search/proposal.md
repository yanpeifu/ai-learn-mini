# Proposal

## Why

大模型的训练数据有截止时间。当用户想学的是一门**很新的知识**时，模型记忆里根本没有它——
比如输入「Harness Engineering」，模型会把它误判成另一个领域的知识，于是**大纲从第一步就跑偏，题目跟着全错**。

这对本项目是致命的：MVP 要验证的核心假设 H1 就是「AI 出题质量足够好」。
而现在的链路是「单次 LLM 调用 → 结构化输出 → 服务端质量校验」，
质量校验（`services/quality.py`）只能检查**结构是否自洽**（答案在不在选项里、选项有没有重复、讲解够不够长），
**查不出事实是否过时或张冠李戴**。也就是说：模型一旦不知道，系统没有任何机制能发现，
只会把错误的题一本正经地发给用户。

同时输入场景已经扩大：用户很可能直接粘贴一个**网页链接**（刚发布的官方文档、新工具的说明页），
而这类内容恰恰是模型最不熟悉、也最需要外部来源的。

现在做的理由：M2 的 LLM 适配层已经落地（自研 `LLMProvider` 门面 + LangChain 实现 + Mock/Fake 双轨），
外挂一个"外部资料获取层"不需要重构既有代码；`.env.example` 也已预留 `TAVILY_API_KEY`。

## What Changes

- 新增**外部知识获取层**，基于 LangChain 官方 Tavily 集成（`langchain-tavily` 的 `TavilySearch` / `TavilyExtract`）：
  - 按关键词检索内容；
  - 按网址抽取整页正文。
- 新增**检索画像（profile）决策**：按知识复杂度、时效性、用户地区动态选参数，并明确区分两类参数——
  - **实例化期参数**（`include_raw_content` / `max_results` / `country`）：用「画像 → 工具实例」的工厂 + 缓存实现，因为官方文档明确这些参数**无法在调用时修改**；
  - **调用期参数**（`search_depth` / `topic` / `time_range` / `include_domains` / `start_date` / `end_date`）：调用时按需传。
- 大纲与出题改为**以外部资料为依据**：检索结果作为「参考资料」注入提示词，
  并新增硬约束——只依据资料出题、资料未覆盖的内容必须显式标注不确定，不得凭记忆编造。
- 输入侧：`raw_text` 若是网址，走 `TavilyExtract` 抓整页正文；
  **该路径不套用 PRD F1 的 20–2000 字校验**（纯文字输入路径的校验维持现状）。
- **失败降级**：无 API Key / 网络不可达 / 限流（429/432/433）/ 超时 → 跳过检索，
  回落到现有纯模型流程，用户无感；后端记日志。
- 新增**每日检索次数上限**，保护每月 1000 免费 credits，并纳入 PRD M3-05 的防滥用要求。
- 检索结果**不落库**，但日志记录来源 URL、检索参数与 credit 消耗，为将来做"来源引用"留存数据。

## Capabilities

### New Capabilities

- `web-knowledge-retrieval`: 外部知识获取能力——按关键词检索与按网址抽取整页正文，
  包含检索画像决策、实例化期/调用期参数分层、失败降级、用量统计与每日限额。
- `grounded-outline-and-questions`: 大纲与题目生成以外部资料为依据的行为契约——
  资料优先于模型记忆、不得越出资料编造、资料不足时的显式降级，以及网址输入的校验规则。

### Modified Capabilities

- （无）项目当前 `openspec/specs/` 为空，没有既有 capability 需要修改。

## Impact

- **代码**：新增 `backend/app/services/search/`（`base.py` 门面 + `profiles.py` 画像决策 +
  `tavily.py` LangChain 适配 + `mock.py` 离线实现）；改动
  `services/prompts.py`、`services/outline_service.py`、`services/question_service.py`、
  `core/config.py`、`core/security.py`、`core/errors.py`、`core/logging.py`、`api/knowledge.py`。
- **依赖**：新增 `langchain-tavily`（锁版本号，与现有 `langchain` 1.x 生态对齐）。
- **配置**：`TAVILY_API_KEY`（`.env.example` 已预留）、检索总开关、超时、
  每日检索上限、强制检索 / 强制关闭开关。
- **接口**：`POST /api/knowledge/outline` 的 `raw_text` 语义扩展为「文本或网址」；
  检索失败不新增面向用户的错误码，只降级 + 记日志。
- **前端**：本次不改（用户把链接直接粘贴进现有输入框）。
- **成本**：Tavily 检索消耗 credits（`basic` = 1、`advanced` = 2、`auto_parameters` = 2）；
  LLM 侧仍守 PRD「单次完整学习（15 题）≤0.05 元」。
- **不影响**：答题、结算、学习记录、举报等既有链路。
