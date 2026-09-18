# MVP 阶段成果总结

> 约定：**每完成一个阶段就更新本文档**，格式为「后端（模块/文件/说明）→ 前端（模块/文件/说明）→ 测试与验证 → 未完成与下一步」。
> 最后更新：2026-09-18（阶段 M0 / M1 / M2 / M3 / M4 / M5 代码完成；M5 的端到端视觉验收进行中）

---

## 阶段总览

| 阶段 | 内容 | 状态 | 验收物 |
| --- | --- | --- | --- |
| M0 | 环境与骨架（后端 + 前端工程） | ✅ 完成 | `GET /api/health` 可访问；Taro 工程可编译 |
| M1 | 数据层（9 张表 + 索引 + 迁移 + CRUD） | ✅ 完成 | `alembic upgrade head` 可建全部表；全链路数据可插入查询 |
| M2 | 出题引擎（LLM 适配层 → 提示词 → 质量校验 → 大纲/出题服务） | ✅ 完成 | 139 个测试全绿；真实端到端（大纲 + 15 题）0 致命问题 0 警告 |
| M3 | 业务接口（登录/大纲/出题/作答/结算/记录/举报/统计） | ✅ 完成 | 后端完整闭环可用：登录 → 生成 → 出题 → 答题 → 结算 → 记录 |
| M4 | 前端骨架（设计令牌 + 公共组件 + 请求层 + 状态） | ✅ 完成 | 手机视口逐项截图与《原型-3-状态与规范》一致 |
| M5 | 五个页面 1:1 还原（原型 18 屏状态） | 🚧 代码完成，视觉验收进行中 | 首页 2 态 + 大纲 2 态已截图核对；答题/结算/我的待验收 |
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

### M2 出题引擎（提示词 / 质量校验 / 生成服务）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 结构化 Schema | `backend/app/schemas/generation.py`、`backend/app/schemas/repair.py` | `OutlinePayload`（3–5 个知识点）、`GeneratedQuestionSet`（含 level_seq）、`QuestionListPayload`（修复/补题返回）；`to_payload()` 可直接喂给质量校验 |
| 提示词 | `backend/app/services/prompts.py` | 大纲提示词（新增）+ 出题提示词（**沿用 `quality_check.py` 已验证的 13 条硬约束**，扩展为 3 关 × 5 题、知识点全覆盖、每关难度梯度）+ 修复提示词 + 补题提示词 |
| 质量校验 | `backend/app/services/quality.py` | **逐项移植 `quality_check.py`**：致命项（答案不在选项 / 选项 key 跳号 / 选项重复 / 题型选项数 / 多选答案 <2 / 「以上都对」/ 题干重复且选项重合 / 知识点引用不存在 / 讲解与答案矛盾）+ 警告项（讲解过短 / 答案集中 / 难度全同 / 知识点未覆盖 / 选项组被 3 题复用）+ 三条「刻意不报」的反例；另加本项目的结构规则（15 题 / 每关 5 题） |
| 统一调用策略 | `backend/app/services/generation.py` | 超时/坏 JSON/网络抖动 → 重试（默认 2 次）；**401/402/403 → 立即中止不重试**；重试耗尽 → 映射成 `LLM_TIMEOUT`/`LLM_BAD_FORMAT`/`GENERATION_FAILED` |
| 大纲生成 | `backend/app/services/outline_service.py` | 输入校验（20–2000 字 + 敏感词，非法输入不消耗模型调用）→ 生成 3–5 个知识点 |
| 出题引擎 | `backend/app/services/question_service.py` | 生成 → 逐题校验 → 单题重生成 → 仍不合格丢弃 → 腾出被冗余知识点占用的位置 → 补题 → 最终结构校验；**任何一步不达标就抛 GENERATION_FAILED，绝不返回不合格题目** |
| 输入安全 | `backend/app/core/security.py` | 字数与敏感词校验，文案与小程序端完全一致（词表为最小可用清单，M8 换完整词库） |
| 冒烟脚本 | `backend/scripts/smoke_pipeline.py` | 一段知识文本 → 大纲 → 15 题 → 输出各关题数 / 重生丢弃补题数 / 致命与警告数 / 成本 |

### M3 业务接口层

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 登录鉴权 | `app/core/auth.py`、`app/api/auth.py`、`app/api/deps.py` | JWT(HS256) 签发/校验；`get_current_user` 从 Bearer token 解 user_id（**不接受前端传 user_id**）；过期/伪造/垃圾 token 一律 401 |
| 微信登录 | `app/services/wechat.py` | 真实 `code2session`；无 AppID 时用 `DEV_LOGIN_ENABLED` 假登录（同一 code 稳定映射同一账号） |
| 知识接口 | `app/api/knowledge.py` | K1 生成大纲 / K2 保存编辑后大纲（<2 个知识点拒绝）/ K3 生成 3 关 × 5 题（重新出题先清旧关卡）/ K4 获取大纲与关卡 |
| 答题接口 | `app/api/attempt.py` | Q1 开始闯关（自动放弃上一次未完成）/ Q2 提交作答 / Q3 结算 / Q4 只读回看 / Q5 学习记录分页 / Q6 继续学习 |
| 判定与结算 | `app/services/attempt_service.py` | 单选/判断完全一致、**多选全对才算对**；提交幂等；答错入错题池；连对统计；结算含正确率/星级/各知识点表现/薄弱点/指向性建议（0 星走安抚文案） |
| 防作弊 | `app/schemas/quiz.py`、`app/services/serializers.py` | 下发结构独立定义且**不含 answer/explanation**，正确答案只在提交后返回（有测试专门断言响应里不出现这两个字段） |
| 限流 | `app/services/quota.py` | 大纲/出题各 20 次/日（可按 `.env` 调整），超限 429 |
| 举报与下线 | `app/api/question.py`、迁移 `0002_question_disabled_at` | ≥N 个**不同用户**举报后自动下线（`REPORT_FLAG_THRESHOLD`，默认 3）；提供 `X-Admin-Token` 保护的人工下线/恢复接口；下线题目不再下发 |
| 我的页统计 | `app/api/user.py`、`app/services/stats_service.py` | 学习次数 / 累计答题 / 平均正确率 / 已学习天数 / 连续学习天数 / 待复习错题数 |
| 首页模板 | `app/constants/templates.py`、`app/api/templates.py` | 6 个模板（含预填文案，**文案待你确认**） |

### M4 前端骨架（Taro 4 + React 18 + TypeScript）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 素材 | `src/assets/mascot.ts`、`src/assets/icons.ts`、`src/utils/svg.ts` | 颜宝 8 表情 + 21 个线性图标。小程序 WXML 不支持 `<svg>` 标签，所以统一转成 SVG data URI 用 `background-image` 渲染（weapp / H5 都支持） |
| 基础组件 | `src/components/{ClayButton,ClayCard,Chip,TipBar,Toast,ProgressBar,Skeleton,Dialog,EmptyState,AppBar,Stepper,Yanbao,Icon}/` | 状态与《原型-3-状态与规范》逐项对齐：按钮 6 态、选项条 7 态 + 判断题变体、卡片两级、进度条 3 档、空状态 / 网络错误 / 生成失败三态 |
| 请求层 | `src/services/request.ts`、`src/services/api.ts` | 统一基址、自动注入 `Authorization`、解包 `{code,message,data}`、超时与 5xx 自动重试（4xx 不重试）、401 清 token；全部接口的类型化封装（大纲 40s / 出题 90s 长超时） |
| 本地能力 | `src/services/storage.ts`、`src/services/feedback.ts` | token 与答题进度本地存储；音效预加载与震动（素材缺失时静默跳过） |
| 状态管理 | `src/store/UserContext.tsx`、`src/store/AttemptContext.tsx` | 启动静默登录（H5 / 无 AppID 时走 DEV 兜底 code）；闯关进度本地 + 服务端双保存 |
| 自定义 tabBar | `src/custom-tab-bar/` | 原型底部「圆角方块图标 + 文字」的实现；默认仍用原生 tabBar，开发者工具验证后把 `tabBar.custom` 改为 `true` |
| 视觉验收页 | `src/pages/dev/components.tsx` | 把原型里每个组件状态渲染成一页用于截图比对（**发布前删除**） |

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
| 单元测试 | 147 | ✅ 全通过 |
| 集成测试（迁移 / 仓储） | 8 | ✅ 全通过 |
| 接口测试（健康检查 / 登录 / 知识 / 答题 / 举报统计） | 61 | ✅ 全通过 |
| **合计** | **216** | ✅ 全绿，覆盖率 **94%** |
| 前端类型检查 | 1 | ✅ `pnpm type-check` 零错误 |
| 前端构建 | 2 | ✅ `pnpm build:weapp`、`pnpm build:h5` 均成功 |
| 真实模型冒烟（单次调用） | 1 | ✅ deepseek-flash 结构化调用成功：6.3s / 177+1117 token / 约 0.0046 元 |
| 真实端到端冒烟（大纲 + 15 题） | 1 | ✅ 5 个知识点、15 题、3 关各 5 题、0 致命问题、0 警告、约 0.0677 元 |
| 后端闭环可用性 | 1 | ✅ Swagger 可完整走通「登录 → 生成大纲 → 出题 → 15 题作答 → 结算 → 学习记录 / 继续学习」 |
| 组件视觉验收 | 4 张截图 | ✅ 手机视口（390×844）下逐项核对：颜宝 8 表情、按钮 6 态、选项条 7 态 + 判断题、标签与进度、卡片层级、空状态与失败态，与《原型-3-状态与规范》一致 |
| 页面视觉验收（H5 + 真实后端 + 真实模型） | 3 态 | ✅ 首页空态（P1-1）、首页校验错误（P1-3，已按原型改为实时校验 + 按钮置灰）、大纲可编辑（P2-2，真实模型生成 5 个知识点）与原型一致 |
| 页面视觉验收（剩余） | 3 页 | ⬜ 答题页 / 结算页 / 我的页：代码完成且编译通过，端到端截图待补（下一阶段先做） |

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
| 测试数据模板化会被判成重复题 | 造合格题数据时给题干与选项加唯一后缀，否则相似度检查会命中 `stem_duplicate`（这是校验器正确工作，不是 bug） |
| 真实成本略超 PRD 目标 | 实测一次完整学习（大纲 + 15 题）约 **0.0677 元**，PRD 目标是 ≤0.05 元（超约 35%）。主因是 15 道题的讲解输出 token 较多。可选优化：① 讲解限定 40–80 字；② 按关分 3 次调用（省不了 token，只影响并发）；③ 接受现状（10 元约可跑 150 次完整学习）。**建议放 M6 统一评估后再定** |
| 「3 人举报下架」在 MVP 不会真实发生 | MVP 里每套题只属于生成它的用户（不共享），所以「3 个不同用户举报同一题」要等 V0.5 分享/挑战上线才会出现。MVP 阶段真正可用的下架入口是 `X-Admin-Token` 保护的人工下线接口；阈值逻辑已按去重人数实现并测试过 |
| H5 白屏：`process is not defined` | 视觉验收时真实踩到：`process.env.TARO_APP_API_BASE` 在 H5 运行时没有被静态替换。已在 `config/index.ts` 用 `defineConstants` 构建期写死后端地址，并在 `.env.development` / `.env.production` 补上该变量 |
| 音效素材缺失 | PRD 要求答对/答错/连对/通关四类音效；代码链路（预加载、音量、静音适配）已完成，但 mp3 素材需要你提供，放到 `src/assets/sounds/` 即可自动生效 |
| 进行中的闯关会泄露答案（已修复） | `GET /api/attempt/{id}` 原本把**未作答题目**的 `correct_answer`/`explanation` 一起返回，抓包即可作弊。已改为「只有已作答的题、或已结算的闯关才返回答案」，并补了回归测试 |
| token 失效后无法自愈（已修复） | 请求层原本只清 token、不重登，页面会一直报「登录状态已过期」。现在 401 会自动重新静默登录一次并重试原请求 |
| 本地后端未跑迁移 → 登录 500（环境） | 启动后端只起了服务、没执行 `alembic upgrade head`，数据库没有表，登录报 `no such table: user`，前端表现为 401。**本地联调必须先跑迁移** |

---

## 四、未完成与下一步

| 项 | 状态 |
| --- | --- |
| M5 收尾：答题页 / 结算页 / 我的页的端到端截图验收（含退出恢复、只读回看、低分结算态） | 下一步立即做 |
| M6 联调与回归（异常路径、边界、真实冒烟、`quality_check.py --reaudit` 回归、成本评估） | 待开始 |
| 杂项：首页 6 个模板的预填文案待确认；`frontend/README.md` 待补；音效素材待提供；`pages/dev/components` 与 `tabBar.custom` 需在开发者工具验证后处理；成本优化待 M6 决策 | 待办 |
