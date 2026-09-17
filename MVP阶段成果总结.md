# MVP 阶段成果总结

> 约定：**每完成一个阶段就更新本文档**，格式为「后端（模块/文件/说明）→ 前端（模块/文件/说明）→ 测试与验证 → 未完成与下一步」。
> 最后更新：2026-09-17（阶段 M0 / M1 / M2-前半）

---

## 阶段总览

| 阶段 | 内容 | 状态 | 验收物 |
| --- | --- | --- | --- |
| M0 | 环境与骨架（后端 + 前端工程） | ✅ 完成 | `GET /api/health` 可访问；Taro 工程可编译 |
| M1 | 数据层（9 张表 + 索引 + 迁移 + CRUD） | ✅ 完成 | `alembic upgrade head` 可建全部表；全链路数据可插入查询 |
| M2 | 出题引擎（LLM 适配层 → 提示词 → 质量校验 → 大纲/出题服务） | 🚧 进行中（适配层已完成，后半进行中） | LLM 适配层单测全绿 + 真实模型冒烟通过 |
| M3 | 业务接口（登录/大纲/出题/作答/结算/记录/举报） | ⬜ 未开始 | Swagger 可走通完整闭环 |
| M4 | 前端骨架（设计令牌 + 公共组件 + 请求层 + 状态） | ⬜ 未开始 | 组件逐状态截图与原型一致 |
| M5 | 五个页面 1:1 还原（原型 18 屏状态） | ⬜ 未开始 | H5 截图与原型逐屏比对 |
| M6 | 联调与回归（异常路径 / 边界 / 真实冒烟 / 质量回归） | ⬜ 未开始 | 测试报告 + 截图对照表 |

---

## 一、后端（FastAPI + SQLAlchemy + LangChain + DeepSeek）

### M0 应用骨架

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 应用入口 | `backend/app/main.py` | FastAPI 实例、lifespan（启动日志/退出释放数据库引擎）、路由注册、trace id 中间件、异常处理器 |
| 配置 | `backend/app/core/config.py` | pydantic-settings；**自动兼容 `.env` 里已有的 `DEEPSEEK_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` / `LLM_TIMEOUT`**；支持 `LLM_PROVIDER`（deepseek/bailian/volcengine/mock）、`LLM_FALLBACKS`、每日限流、业务参数（3 关 × 5 题、20–2000 字等） |
| 统一响应 | `backend/app/core/response.py` | `{code, message, data}` 信封（PRD 2.5） |
| 错误处理 | `backend/app/core/errors.py` | `ErrorCode` 枚举 + `AppError` + 三类全局异常处理器（业务异常 / 参数校验 / 兜底 500）；401/402/403 类技术细节绝不进用户可见文案 |
| 日志与链路 | `backend/app/core/logging.py` | JSON 结构化日志、`X-Trace-Id` 中间件、`log_llm_call`（provider / model / purpose / 耗时 / token / 估算成本） |
| 健康检查 | `backend/app/api/health.py`、`backend/app/api/router.py` | `GET /api/health` 返回统一信封，含 env / version / llm_provider / database |
| 数据库接线 | `backend/app/db/session.py` | 引擎与会话工厂；SQLite 打开外键约束；`get_db` 依赖（成功提交、异常回滚、最后关闭） |

### M1 数据层

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 数据模型 | `backend/app/models/{user,knowledge,quiz,attempt,mistake,report}.py` | 9 张表：user / knowledge_source / knowledge_outline / level / question / attempt / answer_record / mistake / question_report，字段严格对齐 PRD 2.4 |
| 跨库类型 | `backend/app/db/types.py` | `UTCDateTime`（SQLite 与 PostgreSQL 统一「写 UTC、读带时区」）、`JSONVariant`（SQLite=JSON / PostgreSQL=JSONB）、`utcnow()` |
| 声明式基类 | `backend/app/db/base.py` | SQLAlchemy 2.0 `DeclarativeBase` + 约束命名规范（方便后续自动生成迁移） |
| 索引 | 各模型 `__table_args__` | `ix_attempt_user_started`、`ix_attempt_user_status`、`ix_answer_record_attempt`、`ix_question_level_seq`、`ix_mistake_user_next_review`、`ix_question_report_question_status`、`ix_user_openid`（唯一）、`ix_knowledge_source_user`、`ix_knowledge_outline_user` |
| 数据访问层 | `backend/app/repositories/{base,entities}.py` | 通用 CRUD 基类 + 9 个 Repository；含业务方法：`get_or_create_by_openid`、`update_points`、`replace_level_questions`（丢弃不合格题）、`get_ongoing`/`abandon_others`（继续学习）、`has_answered`（提交幂等）、`record_wrong`/`count_due`（错题池与间隔重复）、`is_flagged`（举报 ≥3 次下架） |
| 迁移 | `backend/alembic/env.py`、`backend/alembic/versions/ba9c0649ba60_initial_schema.py` | 首个迁移含全部表与索引；`upgrade head` / `downgrade base` 可逆；SQLite 打开 batch 模式 |

### M2 LLM 适配层（LangChain）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 门面接口 | `backend/app/services/llm/base.py` | 自研 `LLMProvider`（`chat` / `chat_json` / `cost_estimate`）+ `ChatMessage` / `LLMUsage` / `LLMResult` + 错误分类（UNAVAILABLE / TIMEOUT / TRANSIENT / BAD_FORMAT） |
| LangChain 实现 | `backend/app/services/llm/langchain_provider.py` | `init_chat_model(model, model_provider="openai", base_url, api_key, timeout, max_retries)`；`with_structured_output(schema, method, include_raw=True)`；不支持时降级为「文本 + JSON 修复」；401/402/403 立即中止不重试；**自动补 json_mode 所需的 schema 提示**；每次调用写结构化日志。**全项目唯一 import langchain 的文件** |
| JSON 修复 | `backend/app/services/llm/json_repair.py` | 三级降级：去代码块标记 → 去尾逗号 → 截断补齐；**移植自已验证的 `quality_check.py`**，保证线上出题与质检脚本同一套标准 |
| 假模型 | `backend/app/services/llm/mock.py` | `MockProvider`（夹具驱动，0 成本、不联网），支持 `from_fixture_dir` |
| 供应商装配 | `backend/app/services/llm/factory.py` | `build_provider(settings)` 按 `.env` 装配；`FallbackLLMProvider` 主备切换（放在门面层的原因见设计文档 4.3） |
| 冒烟脚本 | `backend/scripts/smoke_llm.py` | 一次真实调用验证链路，只打印 provider/model/耗时/token/成本，不打印任何密钥 |

---

## 二、前端（Taro 4 + React 18 + TypeScript）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 工程初始化 | `frontend/`（官方 `taro init` 生成） | Taro 4.2.1 + React 18.3.1 + TypeScript 5.9 + Sass + Webpack5，全部稳定版 |
| 编译配置 | `frontend/config/index.ts` | `designWidth: 375`（原型就是 375 逻辑像素稿，原型 px 可原样搬进样式）；`sass.resource` 自动注入设计令牌；`alias @`；webpack5 |
| 设计令牌 | `frontend/src/styles/tokens.scss` | 色彩 / 圆角 / 描边（2.5px）/ 三层阴影 / 按压缓动 / 字号，严格对齐《UI设计风格方案》v1.2 |
| 全局样式 | `frontend/src/app.scss` | 纸张底 `#FFFCF7` + 墨线 `#33302E` + 中文字体回退链（不引入字体包，规避 2MB 主包限制） |
| 路由与导航 | `frontend/src/app.config.ts` | 5 个页面（index/outline/quiz/result/mine）+ tabBar（首页/我的）+ 全局自定义导航栏（原型每页自带页头） |
| 页面骨架 | `frontend/src/pages/{index,outline,quiz,result,mine}/` | 每页 `tsx + scss + config` 三件套；M5 阶段按原型 18 屏逐个还原 |
| 工程约束 | `frontend/tsconfig.json`、`frontend/project.config.json`、`frontend/pnpm-workspace.yaml` | `strict: true` + `skipLibCheck`（第三方类型不兼容 webpack-chain）；`urlCheck: false`（本地联调）；pnpm 11 依赖构建脚本白名单 |

---

## 三、测试与验证

| 类型 | 数量 | 结果 |
| --- | --- | --- |
| 单元测试 | 72 | ✅ 全通过 |
| 集成测试（迁移 / 仓储） | 8 | ✅ 全通过 |
| 接口测试（健康检查） | 4 | ✅ 全通过 |
| **合计** | **84** | ✅ 全绿，覆盖率 **91%** |
| 前端类型检查 | 1 | ✅ `pnpm type-check` 零错误 |
| 前端构建 | 2 | ✅ `pnpm build:weapp`、`pnpm build:h5` 均成功 |
| 真实模型冒烟 | 1 | ✅ deepseek-flash 结构化调用成功：6.3s / 177+1117 token / 约 0.0046 元 |

**关掉的关键风险（都是实测，不是推测）**

| 风险 | 结论 |
| --- | --- |
| 本机 Python 3.14 装不上 AI 相关依赖 | 用 `uv` 装独立 Python 3.12，依赖全部可装（FastAPI/SQLAlchemy/LangChain 均正常） |
| 沙箱限制导致 pytest 卡死 | 根因是 `.pytest_cache` 写入被拒；已在 `pyproject.toml` 关掉 cacheprovider |
| `alembic.ini` 读成 GBK 报错 | 该文件必须保持纯 ASCII（已被 Alembic 用系统 locale 解析） |
| autogenerate 迁移缺 import | 生成的迁移已补 `app.db.types` 与 `Text`，并在文件里注明 |
| DeepSeek json_object 模式报 400 | 提示词必须含 "json"；适配层已自动补 schema 提示，业务提示词不用管 |
| LangChain 假模型不支持结构化输出 | 适配层自动降级到「文本 + JSON 修复」，所以单测能完全离线覆盖 |
| pnpm 11 拦截依赖构建脚本 | `pnpm approve-builds --all` + `pnpm-workspace.yaml` 白名单 |

---

## 四、未完成与下一步

| 项 | 状态 |
| --- | --- |
| M2 后半：提示词移植（`quality_check.py` 版）、15 项质量校验规则 + 三类「刻意不报」反例测试、大纲生成服务、关卡出题服务（3 关 × 5 题、缺陷题重生、丢弃补足） | 下一步立即做 |
| M3 业务接口：登录（真实 code2session + DEV 假登录）、大纲保存、关卡下发（**不含 answer**）、开始/作答/结算、记录列表、继续学习、举报、统计、限流 | 待开始 |
| M4 前端骨架：颜宝 8 表情 SVG 组件、ClayButton/ClayCard/OptionItem/ProgressBar 等 10 个公共组件、request 封装、Context 状态、自定义 tabBar | 待开始 |
| M5 五个页面 1:1 还原（原型 18 屏状态 + 音效/震动/中断恢复/只读模式） | 待开始 |
| M6 联调与回归（异常路径、边界、真实冒烟、`quality_check.py --reaudit` 回归） | 待开始 |
| 杂项：`frontend/README.md` 待补；NutUI 尚未引入（M4 决定是否真的需要） | 待办 |
