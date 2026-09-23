# Design

## Context

动机见 `proposal.md`，行为契约见 `specs/`（`web-knowledge-retrieval`、`grounded-outline-and-questions`）。
本节只记录塑造方案的技术事实与现状约束。

**现状（已读代码确认）**

- 生成链路：`api/knowledge.py` → `services/outline_service.py` / `services/question_service.py`
  → `services/generation.py:invoke_json()` → `services/llm/*`（自研 `LLMProvider` 门面，LangChain 只出现在
  `llm/langchain_provider.py`）。业务层没有任何外部资料来源。
- 输入校验：`core/security.py:validate_raw_text()` 统一做「非空 / 20 字下限 / 2000 字上限 / 敏感词」，
  不合法抛 `AppError(INVALID_INPUT, <专用文案>)`。
- 限额：`services/quota.py` 用仓库层计数（`count_since` / `count_with_levels_since`）实现每日上限。
- 错误码：`core/errors.py` 的 `ErrorCode` 枚举 + `_STATUS_BY_CODE` + `DEFAULT_MESSAGES` 三处联动。

**外部技术事实（官方文档核实）**

来自 LangChain 的 Tavily 集成文档与 `tavily-ai/langchain-tavily` 官方 README：

1. `include_answer` 与 `include_raw_content` **只能在实例化时设定，调用时修改无效**（官方原话：这两个参数影响响应体积，不允许在调用时修改）。
2. `max_results`、`country` 同样属于实例化期参数；调用期可改的只有
   `search_depth`、`topic`、`time_range`、`include_domains`、`exclude_domains`、`start_date`、`end_date`、`include_images`。
3. `TavilyExtract` 的 `extract_depth`、`include_images` **可以**在调用时设定。
4. `country` 只在 `topic="general"` 时生效，取值为**小写英文国家名**（如 `china`、`united states`）。

来自 Tavily 官方 Search API 参考：

5. 计费：`basic`/`fast`/`ultra-fast` = 1 credit，`advanced` = 2 credits；`auto_parameters` = 2 credits。
   免费额度为每月 1000 credits。
6. `auto_parameters` 开启时，`include_answer`、`include_raw_content`、`max_results` 仍**必须手动设置**。
7. `language` / `filter_by_language` 可在 API 侧做语言偏置与强过滤，`include_domains_mode`
   提供 `restrict` / `prefer` 两种语义。
8. **实测核对（`langchain-tavily==0.2.18`，用 `inspect` 读真实签名，2026-09-22）**：
   `TavilySearch` 的**实例化期**参数含 `max_results` / `include_raw_content` / `include_answer` /
   `country` / `auto_parameters` / `include_usage` / `exact_match`；**调用期**参数为
   `query`（必填）/ `include_domains` / `exclude_domains` / `search_depth` / `include_images` /
   `time_range` / `topic` / `start_date` / `end_date`。
   `TavilyExtract` 的调用期参数为 `urls`（必填）/ `extract_depth` / `include_images` / `query`，
   实例化期另有 `chunks_per_source` / `format`。
   结论：**`country` 可用**；`language` 与 `filter_by_language` **未被该封装暴露**，
   故语言/地域偏置按 D3 的取舍用调用期手段实现；`include_usage` 可用，作为记录 credits 的依据。

## Goals / Non-Goals

**Goals:**

- 让"模型记忆里没有的知识"也能产出正确的大纲与题目：以外部资料为生成依据。
- 同时支持两条取资料路径：按关键词检索、按用户给出的网址抽取整页正文。
- 检索参数按知识复杂度、时效性、地区动态选择，且**可离线单测、成本可预测、可一键回退**。

**Non-Goals:**

- 不改前端：不加"粘贴链接"入口、不加来源展示 UI（链接直接粘贴进现有输入框）。
- 不做检索结果落库与来源引用（只在日志留痕）。
- 不做分块 / RAG / 长文档多轮出题（PRD 把文档解析归 V1.0）。
- 不引入第二个搜索服务商（只接 Tavily，但保留抽象层）。
- 不改答题、结算、学习记录链路。

## Decisions

### D1 确定性编排：画像 → 工具实例 → 调用（不用 `create_agent`）

**决定**：不采用「把两个工具交给 Agent、让模型自己决定搜什么」的做法。
改为代码侧先算出检索画像，再构造对应参数的检索实例并调用，最后把结果注入提示词。

**理由**：官方文档事实 1、2、6 决定了关键参数（`include_raw_content` / `max_results` / `country`）
无法在运行时切换 —— Agent 自主编排根本改不动它们。此外 Agent 路线行为不确定（可能不检索、可能反复检索）、
无法用 Mock 稳定单测、成本不可预测，与项目既有原则「预生成优于实时调用」「规则模板优于每次调模型」相冲突。

**备选**：`create_agent(model, [tavily_search, tavily_extract])` —— 灵活性更高，但代价如上，本次不采用。

### D2 检索能力放在自研门面之后（唯一 LangChain 接触点）

**决定**：新增 `backend/app/services/search/`：

| 文件 | 职责 |
| --- | --- |
| `base.py` | `SearchProvider` 协议 + 自研数据结构（`SearchHit` / `ExtractResult` / `SearchOutcome`） |
| `profiles.py` | 画像决策**纯函数**：知识复杂度 + 时效性 + 地区 → 参数组合 |
| `tavily.py` | 唯一 `import langchain_tavily` 的地方（`TavilySearch` / `TavilyExtract`） |
| `factory.py` | 按配置装配 provider + 工具实例缓存 |
| `mock.py` | 离线 / CI 用的假实现（fixture 驱动） |

**理由**：与 `services/llm/base.py` 已确立的边界完全一致（框架只允许出现在适配层，业务层只依赖自研接口），
这样业务层可零网络单测，将来换搜索供应商也不动业务代码。边界用一条子进程测试守住（同现有守 `langchain` 边界那条）。

**备选**：业务层直接 `from langchain_tavily import TavilySearch` —— 破坏既有边界、测试必须联网，不采用。

### D3 参数分层：实例化期参数走画像工厂缓存，调用期参数每次传

**决定**：按下表分层处理，工厂以 `(include_raw_content, max_results, country)` 为 key 缓存实例。

| 参数 | 时机 | 由什么决定 |
| --- | --- | --- |
| `include_raw_content` | 实例化 | 知识复杂度（复杂 → 取整页正文；简单 → 只要片段） |
| `max_results` | 实例化 | 知识复杂度（简单 3 条 / 复杂 5–8 条） |
| `country` | 实例化 | 用户地区（仅 `topic="general"`） |
| `search_depth` | 调用期 | 复杂度 + 时效性（`basic` / `advanced`） |
| `topic` | 调用期 | 时效性（时事类 → `news`） |
| `time_range` | 调用期 | 时效性（近一周 / 近一月） |
| `include_domains` | 调用期 | 地区/语言偏置、可信来源白名单 |
| `extract_depth` | 调用期 | 页面复杂度 |

**理由**：这是官方事实 1–4 逼出来的唯一可行形态；缓存让"预实例化复用"与"按需扩展维度"同时成立。

**关于地域偏置的取舍**：`country` 也是实例化期参数，若把国家纳入画像 key，实例组合会随国家数增长，
且 `country` 与 `topic="news"` 不兼容。因此**优先用调用期手段表达地域**
（中文/英文 query + `include_domains` + `topic`），只有确实需要强地域偏置时才把 `country` 纳入画像。

### D4 触发时机：按需判断，且复用已有的那次调用

**决定**：默认 `auto` 模式 —— 在 K1 大纲调用已有的结构化输出里增加「是否需要外部资料 + 检索关键词」字段，
模型判定需要时才发起检索，并用资料重跑一次大纲（最坏情况 2 次大纲调用）。
配置项 `SEARCH_MODE=auto|always|off`。

**理由**：

- 「每次必搜」在官方计费事实 5 下不可接受：`advanced` = 2 credits，1000 credits/月仅够约 500 次。
- 「单独一次轻量判断调用」要多一次往返（+2–5 秒）和一份成本，而复用已有调用几乎免费。
- `.env` 可切 `off` 让线上出问题时一键回退到当前行为。

**备选**：前端加"联网查证"开关 —— 本次不改前端，留到将来。

### D5 参考资料注入与提示词契约

**决定**：`services/prompts.py` 的大纲/出题模板增加可选 `references` 段，渲染为编号的
「参考资料 N｜来源网址」+ 一组硬约束（只依据资料、不得越出资料、资料没覆盖就不要编造）。
新增 `SEARCH_CONTEXT_MAX_CHARS` 作为**注入预算**，超预算按检索相关性顺序截取并记日志。

**重要区分**：这个预算约束的是「塞进模型提示词的资料量」，**不是** PRD 的字数校验。
按已确认的决定，网址抽取出的正文不套用 20–2000 字规则，也不会被静默截断到 2000 字。

### D6 两条路径的失败契约不同

| 失败场景 | 对外行为 | 内部处理 |
| --- | --- | --- |
| 关键词检索失败（无 Key / 超时 / 429 / 432 / 433 / 网络不可达） | **静默降级**，照常生成 | 日志记 `search_degraded` + 原因 |
| 网址抽取失败（页面不可访问 / 被拒 / 超时） | **对用户可见地失败**（复用 `INVALID_INPUT` + 专用文案） | 日志记原因 |
| 检索总开关关闭 / 未配置 Key | 完全不发起请求 | 无 |

**理由**：关键词检索只是"锦上添花"，失败不该阻断用户；而网址抽取是全流程唯一的正文来源，
若静默降级，模型只能对着一个 URL 字符串出题，等于产出垃圾。因此这两条必须区别对待。

**错误码策略**：不新增对外错误码，网址抽取失败复用 `INVALID_INPUT` 并给出专用文案（与
`validate_raw_text` 现有的 `TEXT_TOO_SHORT_MESSAGE` 等用法一致），避免扩大错误码面。

### D7 可观测与每日限额

**决定**：沿用 `core/logging.py` 的模式新增检索调用日志
（kind=search/extract、参数、结果条数、credits、耗时、trace_id，不含正文与用户隐私）。
每日检索上限用**进程内内存计数**实现，并新增配置项（默认值实现时按实测确定）。

**理由**：检索不会产生数据库记录（检索结果不落库），而复用 `quota.py` 那套需要先有计数载体，
为此新增一张表不划算。当前是单实例本地部署，内存计数足够防滥用。

**已知局限**：多实例部署时内存计数不共享、重启即清零。已在代码注释与本节标注；届时换成共享存储即可。

### D8 「未联网核实」的可见载体

**决定**：无可用资料时，在**生成结果文本本身**加显式标注（如知识点说明后缀「（未联网核实）」），
使用户在现有的大纲确认页即可看到，零前端改动。

**备选**：新增响应字段由前端展示 —— 本次不改前端，不采用。

## Risks / Trade-offs

- [Tavily 域名在国内网络可能不可达] → 失败即降级（D6）；抽象层已预留换供应商；部署时可配代理。
- [超长网页正文推高成本并挤占上下文] → `SEARCH_CONTEXT_MAX_CHARS` 注入预算 + 记录知识源实际长度；
  若实测仍撑不住，再评估分块（属 PRD V1.0 范畴）。
- [`advanced` 检索 2 credits，免费额度 1000/月] → 默认按需检索 + 每日限额 + 逐次记录 credits。
- [langchain-tavily 实际暴露的参数集与官方 API 不一致] → 实现前用 `inspect.signature` 核对真实签名；
  未被封装暴露的 API 参数（如 `language` / `chunks_per_source`）改用调用期替代手段
  （中文/英文 query + `include_domains`），不因此更换 SDK。
- [模型可能无视资料、继续按记忆作答] → 提示词硬约束 + 既有服务端质量校验照旧生效；
  资料未覆盖时按 spec 显式标注而不是编造。
- [「未联网核实」标注污染知识点文本] → 只在确实无资料时添加，有资料路径不受影响。
- [内存限额计数在多实例下不准] → 见 D7 已知局限，当前部署形态下可接受。
- [新增外部依赖] → `langchain-tavily` 锁版本；未配置 Key 时行为与现状完全一致。

## Migration Plan

1. 先落 `search/` 模块与配置项（此时默认行为与现状一致）。
2. 接入大纲：按需判断 → 检索 → 资料注入 → 显式标注。
3. 接入出题：资料注入 + 既有质量校验回归。
4. 最后在 `.env` 打开 `TAVILY_API_KEY` 做真实冒烟。

**回滚**：`.env` 设 `SEARCH_MODE=off`（或移除 `TAVILY_API_KEY`）即回到当前行为，无需回滚代码。

**数据迁移**：无 —— 本次不新增表、不改表结构、不改 Alembic 迁移。

## Open Questions

- **已结（2026-09-22）**：`langchain-tavily==0.2.18` 的真实参数集已用 `inspect` 核对，结论见
  「外部技术事实」第 8 条 —— `country` 可用、`language` / `filter_by_language` 未被封装暴露、
  `include_usage` 可用于记录 credits；参数分层表（D3）无需改动。
- 注入预算 `SEARCH_CONTEXT_MAX_CHARS` 的默认值，需用一次真实网页（含长文）实测后确定。
