# ai-learn-mini · 后端（FastAPI）

## 环境

- Python 3.12（用 `uv` 建的独立虚拟环境：`backend/.venv`）
- 依赖清单见 `pyproject.toml`

```powershell
# 1) 建环境并装依赖（需要联网）
cd E:\CodexProjects\ai-learn-mini\backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r <(uv pip compile pyproject.toml)

# 2) 启动（开发期）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 3) Swagger
# http://127.0.0.1:8000/docs

# 4) 测试（默认全部使用 Mock/Fake，不联网、不花钱）
.\.venv\Scripts\python.exe -m pytest
$env:COVERAGE_FILE="$env:TEMP\.coverage_ai_learn"
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

### 开发机上的两个小坑（已处理）

1. **pytest 会卡住**：本机沙箱限制 Python 进程在项目目录内新建文件，pytest 写 `.pytest_cache` 时会被拒绝。
   已在 `pyproject.toml` 的 `addopts` 里加 `-p no:cacheprovider` 规避。
2. **SQLite 文件与构建产物**：同理，后端默认库文件 `backend/ai_learn.db`、前端 `dist/` 属于"新写入文件"，
   在受限沙箱里需要授权执行；调试时可用环境变量把库指到临时目录：

   ```powershell
   $env:DATABASE_URL="sqlite:///$env:TEMP\ai_learn_dev.db"
   ```

## 配置

配置优先级：**环境变量 > `backend/.env` > 项目根 `.env` > 代码默认值**。
项目根目录的 `.env` 里已有的 `DEEPSEEK_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` / `LLM_TIMEOUT`
会被自动识别（不用改原有文件）。

新增的 LLM 相关变量（切换供应商只改这些，不动代码）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | `deepseek` / `bailian` / `volcengine` / `mock` |
| `LLM_STRUCTURED_METHOD` | `json_mode` | `json_schema` / `function_calling` / `json_mode` |
| `LLM_FALLBACKS` | 空 | 逗号分隔的备用供应商，如 `bailian,volcengine` |
| `BAILIAN_API_KEY` / `BAILIAN_MODEL` | 空 / `qwen-plus` | 阿里云百炼 |
| `VOLCENGINE_API_KEY` / `VOLCENGINE_MODEL` | 空 / `doubao-seed-1-6` | 火山方舟 |
| `DEV_LOGIN_ENABLED` | `false` | 本地用假 openid 登录（无 AppID 时） |
| `DAILY_OUTLINE_QUOTA` / `DAILY_LEVEL_QUOTA` | `20` / `20` | 单用户每日生成次数上限 |

### 联网检索（Tavily，选填）

给「AI 解析知识大纲、生成题目」提供外部资料来源：按关键词搜资料，或按用户给出的**网址**抓整页正文。
**不配 `TAVILY_API_KEY` 就是关闭状态**，行为与改动前完全一致。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TAVILY_API_KEY` | 空 | 留空 = 关闭检索；填了才启用 |
| `SEARCH_MODE` | `auto` | `auto` 按需检索 / `always` 每次都搜 / `off` 完全关闭 |
| `SEARCH_CONTEXT_MAX_CHARS` | 见 `config.py` | 注入提示词的资料预算（不是输入框的字数校验） |
| `DAILY_SEARCH_QUOTA` | 见 `config.py` | 单用户每日检索次数上限（保护每月 1000 免费 credits） |

依赖包固定为 `langchain-tavily==0.2.18`（与 `langchain` 1.x 生态对齐）。

**参数分层（已用 `inspect` 核对真实签名，不是照文档猜）**

官方 API 支持的参数，LangChain 封装不一定都暴露；实测该版本的真实边界如下：

| 工具 | 只能在**创建时**设定（调用时改无效） | 可以在**调用时**传 |
| --- | --- | --- |
| `TavilySearch` | `max_results`、`include_raw_content`、`include_answer`、`country`、`auto_parameters`、`include_usage`、`exact_match` | `query`(必填)、`include_domains`、`exclude_domains`、`search_depth`、`time_range`、`topic`、`start_date`、`end_date`、`include_images` |
| `TavilyExtract` | `chunks_per_source`、`format` | `urls`(必填)、`extract_depth`、`include_images`、`query` |

两个由此而来的实现约束：

1. 「动态调整查询力度」必须做成**先决定档位 → 再创建对应工具 → 再调用**，不能指望调用时临时改；
2. `language` 与 `filter_by_language` **未被该封装暴露**，所以面向国内外用户的偏置改用调用期手段
   （中文/英文关键词 + `include_domains` 限定来源站点）；需要强地域偏置时才用创建期的 `country`
   （注意它只在 `topic="general"` 时生效）。

## LLM 适配层（LangChain）

业务代码只依赖自研门面 `app/services/llm/base.py` 的 `LLMProvider`（`chat` / `chat_json` /
`cost_estimate`），`import langchain` 只出现在 `app/services/llm/langchain_provider.py` 一个文件里。
有一条单元测试用**独立子进程**守着这条边界。

| 关注点 | 实现 |
| --- | --- |
| 供应商切换 | 改 `.env` 的 `LLM_PROVIDER` + 对应 Key，不动代码；`LLM_FALLBACKS` 可配主备 |
| 结构化输出 | `with_structured_output(schema, method=..., include_raw=True)`；模型不支持时自动降级为「文本 + 三级 JSON 修复」 |
| JSON 修复 | 移植 `quality_check.py` 里已验证的 extract → 去尾逗号 → 截断补齐（保证线上与质检脚本同一套标准） |
| 错误分类 | 401/402/403 立即中止不可重试（`LLM_UNAVAILABLE`）；超时 `LLM_TIMEOUT`；429/5xx `LLM_TRANSIENT`；解析失败 `LLM_BAD_FORMAT` |
| 可观测 | 每次调用写一条 JSON 日志：provider / model / purpose / 耗时 / token / 估算成本 |
| 测试 | 单测全部用 LangChain 官方假模型与自研 `MockProvider`，零网络零成本 |

### 真实模型冒烟

```powershell
.\.venv\Scripts\python.exe scripts\smoke_llm.py      # 一次很短的调用，约 0.001 元
```

> 注意：`json_mode` 下 DeepSeek 要求提示词里出现 "json"，适配层会自动补一条带字段结构的 system 提示
> （实测：漏掉会直接返回 400）。业务提示词不必自己记这件事。
