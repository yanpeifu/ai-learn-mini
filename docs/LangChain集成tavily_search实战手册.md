# LangChain 集成 tavily_search 实战手册（以本项目为例）

> 案例：`openspec/changes/ground-outline-and-questions-with-web-search`
> 目标：让 AI 出题前先去网上取资料，解决"模型没学过的知识被答成别的领域"。

## 怎么读这份手册

每个知识点都是三段式：

1. **是什么** —— 这个概念本身（用大白话讲，术语保留但会解释）；
2. **项目里怎么实现的** —— 对应哪个文件、哪段代码；
3. **要注意什么** —— 真实踩过或差点踩到的坑。

---

## 一、先看地图：一次"新知识"请求里，检索发生在哪

```
用户输入（文字 或 网址）
   │
   ├─ 是网址？→ TavilyExtract 抓整页正文 ──────────────┐
   │                                                  │
   ▼                                                  ▼
第一次「大纲」调用（模型顺带判断：这段内容需不需要最新资料？）
   │
   ├─ 需要 → TavilySearch 按关键词取资料 → 带资料重跑一次「大纲」
   │
   ├─ 不需要 / 搜不到 / 没配 Key → 大纲照常出，但知识点带上「（未联网核实）」
   ▼
「出题」阶段 → 按知识点再取一次资料 → 生成 15 题 → 服务端质量校验
```

对应文件分布：

| 环节 | 文件 |
| --- | --- |
| 对外接口（门面） | `backend/app/services/search/base.py` |
| 参数决策（画像） | `backend/app/services/search/profiles.py` |
| Tavily 适配（唯一碰 LangChain 的地方） | `backend/app/services/search/tavily.py` |
| 取资料编排 + 限额 + 日志 | `backend/app/services/search/grounding.py`、`quota.py` |
| 离线替身 | `backend/app/services/search/mock.py` |
| 装配 | `backend/app/services/search/factory.py`、`main.py`、`api/deps.py` |
| 接入生成 | `outline_service.py`、`question_service.py`、`level_service.py`、`prompts.py` |

---

## 二、知识点

### KP1 检索门面（SearchProvider）

**是什么**
"门面"就是一层**给你的业务代码看的简化接口**。检索这件事对外只暴露两个动作：按关键词搜、按网址抓。业务代码只认这两个动作，不认底下用的是 Tavily 还是别的服务。

**项目里怎么实现的**
`backend/app/services/search/base.py`：

```python
@runtime_checkable
class SearchProvider(Protocol):
    name: str
    def search(self, queries, profile) -> SearchOutcome: ...
    def extract(self, url, profile) -> ExtractOutcome: ...
```

`Protocol` 是 Python 的"结构约定"：只要一个类有这两个方法，它就算实现了这个接口，不需要显式继承。测试里的假实现就是靠这条成立的。

**要注意什么**

- **失败要用"返回值"表达，不要抛异常。** `SearchOutcome.degraded=True` + `reason` 表示"这次没拿到资料"，业务层看到它就照常生成。如果改成抛异常，每处调用都得写 `try`，降级逻辑会散得到处都是。
- **门面里不要出现 LangChain 的类型。** `SearchHit` / `SearchOutcome` / `ExtractOutcome` 都是自研数据结构；一旦把 LangChain 的 `Document` 之类的类型写进接口，业务层就被框架绑住了。

---

### KP2 创建期参数 vs 调用期参数（本次架构的根因）

**是什么**
LangChain 的 Tool 是**对象**：创建这个对象时能设一批参数（创建期 / 实例化期参数），调用它时又能传一批参数（调用期 / invoke 参数）。**两批不一样**，而且有些参数只能在创建期设。

**项目里怎么实现的**
`base.SearchProfile` 把两批参数分开存放，并只把创建期参数放进缓存 key：

```python
@property
def tool_key(self) -> tuple[bool, int, str | None]:
    """工具实例的缓存 key：只包含「建工具时才能定」的参数。"""
    return (self.include_raw_content, self.max_results, self.country)
```

`tavily._search_tool()` 用 `@lru_cache(maxsize=32)` 按这个 key 缓存工具实例。实测边界（`langchain-tavily==0.2.18`）：

| 只能创建期设 | 调用期也能设 |
| --- | --- |
| `max_results`、`include_raw_content`、`include_answer`、`country`、`auto_parameters`、`include_usage`、`exact_match` | `query`、`search_depth`、`topic`、`time_range`、`include_domains`、`exclude_domains`、`start_date`、`end_date`、`include_images` |

**要注意什么**

- **调用期传创建期参数会被工具直接拒绝**：源码里有一份 `forbidden_params` 清单，传了就报错。所以"动态调整力度"只能做成「先定档位 → 再创建工具 → 再调用」。
- **创建期设了 `search_depth`，调用期传的值会被忽略**（源码里是 `self.search_depth if self.search_depth else search_depth`）。配合 `lru_cache` 复用实例，结果是上一批请求的档位会"粘"到下一批。所以我们的工具实例**刻意不设** `search_depth` / `topic` / `time_range` / `include_domains`。

---

### KP3 适配层边界：只有 `tavily.py` 能 import LangChain

**是什么**
"适配层"= 把第三方库的用法全部关在一个文件里，其他地方只认自研接口。这样将来换供应商（比如换成国内的搜索服务）只改这一个文件。

**项目里怎么实现的**

- `backend/app/services/search/tavily.py` 是唯一 `import langchain_tavily` 的文件；
- 而且这个 import 写在**函数内部**（`_search_tool` / `_extract_tool` 里），叫**延迟 import**——不用检索的部署根本不会加载这个包；
- `factory.build_search_provider()` 在未配置 Key 时返回 `NoopSearchProvider`，连 `tavily.py` 都不会 import。

有一组测试专门守这条边界：

```python
def test_only_the_adapter_imports_langchain_tavily() -> None:
    import_pattern = re.compile(r"^\s*(?:from|import)\s+langchain_tavily", re.MULTILINE)
    offenders = [p for p in app_root.rglob("*.py")
                 if import_pattern.search(p.read_text(encoding="utf-8")) and p.name != "tavily.py"]
    assert offenders == []
```

**要注意什么**

- **静态检查要匹配 import 语句，不能匹配整段文本。** 我第一版写成"文件内容里有没有出现 `langchain_tavily`"，结果把**注释**也判成违规。
- 另有两条**子进程**测试（`subprocess`）断言"只 import 门面时，`sys.modules` 里不应出现 langchain_tavily"。为什么必须在独立进程里跑？因为同一次 pytest 运行里其他测试会加载它，在进程内判断会得出错误结论。

---

### KP4 TavilySearch 的两种失败形态

**是什么**
调用一个 LangChain Tool，失败**不一定表现为抛异常**。这个工具内部把大部分错误吞掉、当成返回值发回来。

**项目里怎么实现的**
源码里的真实逻辑（`langchain_tavily/tavily_search.py`）：

```python
except ToolException:
    raise                                  # 只有"搜不到结果"才抛
except Exception as e:
    return {"error": e}                    # HTTP 401/429、网络错误…… 全被吞成返回值
```

所以适配层要主动把这个返回值还原成异常（`tavily._raise_if_wrapped_error`）：

```python
def _raise_if_wrapped_error(raw):
    if isinstance(raw, dict) and raw.get("error"):
        error = raw["error"]
        raise error if isinstance(error, BaseException) else RuntimeError(str(error))
```

另外创建工具时传 `handle_tool_error=False`，让"搜不到结果"的 `ToolException` 也以异常形式冒出来，这样失败路径只有一种处理方式。

**要注意什么**

- **只看 `type(result) == dict` 就宣布成功是错的**——`{"error": ...}` 也是 dict。我自己就这么误判过一次，把 401 当成了"调用成功"。
- 判断成功要用**语义**：有 `results` 且非空才算拿到资料；本项目里统一在 `_hits_of()` 里做。

---

### KP5 错误归类（classify_error）

**是什么**
把上游五花八门的错误，归一成我们自己的几个原因码，供"要不要降级、日志怎么写"使用。

**项目里怎么实现的**
`tavily.classify_error()`：

```python
_STATUS_TO_REASON = {"401": 未授权, "402": 未授权, "403": 未授权,
                     "429": 被限流, "432": 被限流, "433": 被限流}
_STATUS_PATTERN = re.compile(r"Error (\d{3})")
```

上游的报错文案形如 `Error 401: Unauthorized: missing or invalid API key.`，没有独立的状态码字段，所以只能**从消息里解析**。超时则按异常类名/文案判断，空结果按固定文案判断。

**要注意什么**

- 这是"跟着上游文案走"的脆弱点：**换供应商或上游改文案时要一起改**，所以它被单独抽成一个函数、并且有表驱动单测覆盖 401/403/429/432/433/超时/空结果七种情况。
- 归类结果只用来**记日志和决定降级**，不直接给用户看（对外文案统一是"这个链接读不了"之类）。

---

### KP6 TavilyExtract：按网址抓整页正文

**是什么**
另一个工具：给它一个网址，它把页面正文抓下来（相当于"帮我读这个网页"）。

**项目里怎么实现的**
`tavily._extract_tool()` + `TavilySearchProvider.extract()`：

```python
raw = tool.invoke({"urls": [url], "extract_depth": profile.extract_depth})
text = raw["results"][0].get("raw_content") or ...     # 取抓到的正文
```

`extract_depth`（basic / advanced）是**调用期**参数，可以按页面复杂度临时决定；而 `chunks_per_source` / `format` 是创建期参数，调用时传会被拒绝。

**要注意什么**

- **这条路径不套用输入框的 20–2000 字校验**（网页正文通常远超上上限），但仍要过敏感词检查——见 `outline_service.resolve_knowledge_source()`。
- **抽取失败不走静默降级**，而是抛一个用户可见的错误（"这个链接没能读到内容…"）。理由：此时模型手里只有一个网址字符串，继续出题等于瞎编。这跟"关键词检索失败"的处理**刻意不同**。

---

### KP7 检索画像（profile）：按知识特征决定查多深

**是什么**
"画像"就是一张**规则表**：根据知识复杂度、时效性、用户地区，决定这次检索用哪些参数。

**项目里怎么实现的**
`profiles.build_profile()` 是**纯函数**（同样输入永远同样输出，不碰网络、不碰数据库）：

```python
include_raw_content = 复杂知识          # 复杂 → 连整页正文一起拿
max_results         = 复杂 ? 上限 : 下限
search_depth        = 复杂 ? "advanced" : "basic"
topic               = 强时效 ? "news" : "general"
time_range          = 强时效 ? "month" : None
country             = （只在中文用户 且 topic=general 时）settings.search_country
include_domains     = 中文用户 ? 优先站点白名单 : 空
```

**要注意什么**

- **`country` 只在 `topic="general"` 时生效**（官方 API 的硬限制），所以 `topic="news"` 时必须把它清空——这条单独有测试守着。
- **中文/地域偏置优先用调用期手段**（中文关键词 + `include_domains`），因为 `country` 是创建期参数，一旦纳入缓存 key，实例组合会随国家数量膨胀。
- 纯函数的好处是**可以表驱动测试**：五种输入（简单 / 复杂 / 强时效 / 国内 / 国外）各自断言创建期与调用期参数，测试里零网络。

---

### KP8 取资料编排（gather_references）与注入预算

**是什么**
把前面几个零件串成一条"安全取资料"的流水线：检查开关 → 检查限额 → 生成画像 → 调检索 → 裁剪资料 → 记日志。**整段不抛异常**。

**项目里怎么实现的**
`grounding.gather_references()` 的顺序：

```python
if settings.search_effective_mode == "off":  → 直接返回「没资料（未配置/已关闭）」
if 今日检索次数超限:                          → 直接返回「没资料（超限）」
profile = build_profile(traits, settings)
outcome = provider.search(queries, profile)   # 用 try/except 兜住任何意外
record_search_usage(user_id)                  # 计数
references, trimmed = trim_references(outcome.hits, settings.search_context_max_chars)
logger.info("联网检索完成…", extra={hits, credits, latency_ms, sources, ...})
```

**要注意什么**

- **注入预算（`SEARCH_CONTEXT_MAX_CHARS`）不是输入框的字数校验。** 它约束的是"塞进模型提示词的资料量"，目的是保护模型上下文；输入框那套 20–2000 字只作用于纯文字输入。
- **日志只记来源 URL，不记正文**：`sources` 字段最多列 5 条 URL。正文可能很长、也可能含用户隐私内容。
- 函数签名里有个 `user_id`，为 `None` 时跳过限额计数——脚本与测试用这种方式绕过限额，线上走真实用户 id。

---

### KP9 每日检索限额（进程内计数）

**是什么**
防止有人刷免费额度：单用户每天最多检索 N 次。

**项目里怎么实现的**
`quota.py` 末尾那段（与生成次数限额不同，这里是**内存计数**）：

```python
_search_usage: dict[tuple[int, str], int] = {}      # key = (用户 id, 日期)
_search_lock = threading.Lock()                     # 多线程安全
search_quota_exceeded(user_id, settings) -> bool
record_search_usage(user_id, count=1)
reset_search_usage()                                # 测试专用
```

**要注意什么**

- **超限是"降级"不是"报错"**：到上限后直接按"没资料"继续生成，用户仍能拿到大纲和题目。这跟"生成次数用完就报错"是两种口径，别写混。
- **内存计数的已知局限**：多实例部署时不共享、进程重启即清零。当前是单实例部署，够用；将来水平扩容要换成共享存储（比如 Redis）。
- 用 `threading.Lock` 是因为 FastAPI 的同步接口跑在线程池里，并发是真实存在的。

---

### KP10 把资料注入提示词（render_references）

**是什么**
把检索到的资料变成提示词里的一段文字，并附上"只准依据资料"的硬规则。

**项目里怎么实现的**
`prompts.render_references()` 生成这样的段落：

```
【参考资料】
[1] 标题｜https://来源网址
正文或摘要

【参考资料使用规则（优先级最高）】
1. 上面的参考资料来自联网检索，是本次生成的事实依据，优先级高于你自己的记忆。
2. 只依据参考资料讲事实；参考资料没有写到的内容不要凭记忆补充，也不要编造。
3. 参考资料与你的记忆冲突时，一律以参考资料为准。
4. 参考资料不足以支撑某个知识点时，不要为它编造内容。
```

四个提示词模板（大纲 / 出题 / 重写不合格题 / 补题）都带 `{references}` 占位符。

**要注意什么**

- **没有资料时返回空字符串**，提示词与改动前**一字不差**——这是"可一键回退"的基础。
- 规则写在**渲染出来的段落里**（而不是散落在四个模板中），四个模板才能共用同一套口径。
- 资料正文优先用 `raw_content`（整页正文），没有才退到 `content`（搜索摘要）。

---

### KP11 扩展结构化输出要"向后兼容"

**是什么**
让模型在一次调用里多吐几个字段（要不要联网、用什么关键词、知识复杂度、时效性），用来驱动后面的检索决策。

**项目里怎么实现的**
`schemas/generation.py` 的 `OutlinePayload` 新增四个字段，**全部带默认值**：

```python
needs_external_reference: bool = False
search_queries: list[str] = Field(default_factory=list)
complexity: Literal["simple", "complex"] = "simple"
timeliness: Literal["stable", "time_sensitive"] = "stable"
```

同时在 `prompts.OUTLINE_USER_TEMPLATE` 的 json 结构里加上这几个键，并用第 7–9 条硬性约束说明什么时候填什么。

**要注意什么**

- **必须给默认值**：所有既有测试和假数据（`tests/fakes.py` 的 `outline_payload()`）都不含这几个字段，没有默认值就会直接校验失败、一次打挂几十个测试。
- 判断字段要**写在同一次调用里**，不要为它单开一次模型调用——那要多花 2–5 秒和多一份成本。

---

### KP12 「未联网核实」标注

**是什么**
没有任何外部资料可用时，把"这份内容没经过网上核对"**显式写进用户看得到的地方**，而不是假装很有把握。

**项目里怎么实现的**
`outline_service.annotate_unverified()`：

```python
UNVERIFIED_MARK = "（未联网核实）"
points = [p.model_copy(update={"summary": f"{p.summary}{UNVERIFIED_MARK}"})
          for p in payload.points]
```

**要注意什么**

- 这是**用户可见的行为变化**：默认部署没配 Key 时，所有大纲都会带这个标注。如果哪天想改成"只有检索启用时才标注"，记得**同时改 spec 里的场景**，否则文档和实现就对不上了。
- 标注是**生成之后**加在服务端的，模型看不到它，所以不会污染后续出题。

---

### KP13 依赖注入与延迟 import

**是什么**
把检索实现装配到应用里，让接口能拿到它——同时保证"不用检索"时不加载多余的包。

**项目里怎么实现的**

```python
# main.create_app()
app.state.search_provider = build_search_provider(settings)

# api/deps.py
def get_search_provider(request: Request) -> SearchProvider:
    return request.app.state.search_provider
SearchDep = Annotated[SearchProvider, Depends(get_search_provider)]

# factory.py —— tavily 的 import 写在函数内部
def build_search_provider(settings):
    if not settings.search_enabled:
        return NoopSearchProvider()
    from app.services.search.tavily import TavilySearchProvider   # 延迟 import
    return TavilySearchProvider(settings)
```

**要注意什么**

- 依赖注入（把对象挂在 `app.state` 上、用 `Depends` 取）的好处是**测试里可以直接替换**：API 测试把 `app.state.search_provider` 换成假实现，就不用联网。
- 延迟 import 让"未配 Key"的部署**完全不加载** `langchain_tavily`，冷启动更快、依赖面更小；这条由子进程测试守着。
- `.env` 里的变量名必须与 `config.py` 的字段对应（`search_mode` ↔ `SEARCH_MODE`）。我一开始在 `.env.example` 里写了 `TAVILY_BASE_URL` 这种"看起来合理"的名字，代码根本不读——读不到的配置项只会误导人。

---

### KP14 测试替身与真实冒烟

**是什么**
两类验证：**离线替身**保证逻辑正确且零成本；**真实冒烟**验证"接上真服务也能用"。

**项目里怎么实现的**

| 替身 | 用途 |
| --- | --- |
| `NoopSearchProvider` | 模拟"检索被关闭"，任何调用都不发请求 |
| `MockSearchProvider` | 预置结果 / 可注入失败原因，走通检索与抽取两条路径 |
| `tests.fakes.ScriptedProvider` | 模型侧的脚本化返回（按顺序发结果，塞异常即可模拟失败） |

真实冒烟脚本：`backend/scripts/smoke_search.py`

```powershell
.\.venv\Scripts\python.exe scripts\smoke_search.py --repeat 3        # 新知识：关键词检索
.\.venv\Scripts\python.exe scripts\smoke_search.py --url https://…   # 网址输入：抓整页正文
```

**要注意什么**

- **工具实例是 `lru_cache` 的，测试之间必须清缓存**：`tavily._search_tool.cache_clear()`，否则前一个测试的配置会污染后一个。
- **日志断言别用 pytest 的 `caplog`**：应用初始化用了 `dictConfig(disable_existing_loggers=True)`，logger 可能处于 disabled 状态——单跑该文件能过、全量跑就抓不到日志。正确做法是临时挂一个 `logging.Handler` 并临时把 `logger.disabled` 设回 `False`。
- **只有真实冒烟能验证鉴权**：单测里检索是假对象，Key 填错也全绿。本次就是 294 个测试全过后，第一次真实冒烟才发现 Key 无效。
- 排 401 的顺序：先看**返回体内容**（不是异常）→ 再确认环境变量没覆盖 `.env` → 最后才怀疑 Key 本身。

---

## 三、配置项速查（都在 `.env`）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `TAVILY_API_KEY` | 空 | 留空 = 完全关闭检索；填了才启用 |
| `SEARCH_MODE` | `auto` | `auto` 按需检索 / `always` 每次都搜 / `off` 完全关闭 |
| `SEARCH_TIMEOUT` | `20` | 单次检索超时（秒） |
| `SEARCH_MAX_RESULTS_MIN` / `MAX` | `3` / `8` | 简单知识取下限，复杂知识取上限 |
| `SEARCH_MAX_QUERIES` | `3` | 一次生成最多用几个检索词 |
| `SEARCH_CONTEXT_MAX_CHARS` | `20000` | 注入提示词的资料预算（不是输入框的字数校验） |
| `DAILY_SEARCH_QUOTA` | `30` | 单用户每日检索次数上限 |
| `SEARCH_COUNTRY` | 空 | 地域偏置（小写英文国家名，仅 `topic=general` 生效） |
| `SEARCH_PREFERRED_DOMAINS` | 空 | 优先来源站点，逗号分隔（走 `include_domains`） |

## 四、命令与验证速查

```powershell
# 单测（零网络零成本）
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing

# 真实签名核对（改参数前先跑这个）
.\.venv\Scripts\python.exe -c "from langchain_tavily import TavilySearch; print(sorted(TavilySearch.model_fields)); print(sorted(TavilySearch().args))"

# 真实冒烟（花钱，但唯一能验证真实鉴权与检索质量）
.\.venv\Scripts\python.exe scripts\smoke_search.py --repeat 3
.\.venv\Scripts\python.exe scripts\smoke_search.py --url https://…

# 一键回退（改配置，不改代码）
#   .env 里设 SEARCH_MODE=off（或清空 TAVILY_API_KEY）
```

本次实测参考值：连续 3 次「新知识 → 大纲 → 15 题」全部通过、每次 0 致命问题、3 次模型成本约 0.18 元、检索共 12 credits、单次检索 18–34 秒。
