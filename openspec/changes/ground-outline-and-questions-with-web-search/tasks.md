# Tasks

## 1. 依赖与配置（先落地，保证默认行为与现状一致）

- [x] 1.1 在 `backend/pyproject.toml` 增加 `langchain-tavily` 并锁版本号，装到 `backend/.venv`；验证：`.\.venv\Scripts\python.exe -c "import langchain_tavily; print(langchain_tavily.__name__)"` 能打印出模块名
- [x] 1.2 用 `inspect.signature` 核对 `TavilySearch` / `TavilyExtract` 的真实参数集（`country` 是否可用、`language` / `chunks_per_source` 是否透传、哪些只能在实例化期设），把结论写进 `backend/README.md` 并把 `design.md` 的对应 Open Question 结掉；验证：签名核对结论已落档，且与 design.md 的参数分层表无冲突
- [x] 1.3 在 `backend/app/core/config.py` 增加检索相关配置（`TAVILY_API_KEY`、检索模式 `SEARCH_MODE=auto|always|off`、超时、结果条数上下限、注入预算 `SEARCH_CONTEXT_MAX_CHARS`、每日检索上限、地域/语言偏置），并在 `.env.example` 同步说明；验证：`tests/unit/test_config.py` 新增用例通过，且**未配置 Key 时 `SEARCH_MODE` 生效为关闭**

## 2. 检索门面与画像决策

- [x] 2.1 新建 `backend/app/services/search/base.py`：`SearchProvider` 协议与自研数据结构（检索结果项、抽取结果、本次检索结果汇总），不 import 任何 `langchain*`；验证：新增单测用假实现替换 provider，业务层代码在无网络下可跑通
- [x] 2.2 新建 `backend/app/services/search/profiles.py`：把「知识复杂度 + 时效性 + 用户地区」映射成参数组合的**纯函数**；验证：表驱动单测覆盖「简单知识 / 很新或复杂知识 / 强时效内容 / 国内用户 / 国外用户」五种输入，断言实例化期参数与调用期参数各自正确
- [x] 2.3 新建 `backend/app/services/search/mock.py`：读 fixture 的离线实现；验证：单测用该实现走通「关键词检索」与「网址抽取」两条路径，全程零网络
- [x] 2.4 新建 `backend/app/services/search/tavily.py`：**唯一** `import langchain_tavily` 的文件，封装 `TavilySearch` / `TavilyExtract` 调用、工具实例缓存与错误映射；验证：单测覆盖 401 / 429 / 超时三类错误的映射，另加一条子进程测试断言除本文件外无任何模块 import `langchain_tavily`
- [x] 2.5 新建 `backend/app/services/search/factory.py`：按配置装配 provider（未配 Key 或 `SEARCH_MODE=off` 时装配不发起任何请求的空实现）；验证：单测断言这两种配置下不会产生任何网络调用

## 3. 输入识别与降级路径

- [x] 3.1 实现网址识别：从 `raw_text` 中提取网址（纯网址 / 网址加说明文字两种形态）；验证：单测覆盖纯网址、网址+文字、多个网址、含 www 的网址、普通文字五种输入，断言识别结果正确
- [x] 3.2 当输入含网址时改走 `TavilyExtract` 抽取正文，并**跳过 20–2000 字校验**；验证：单测断言一份远超 2000 字的抽取正文不再被 `INVALID_INPUT` 拒绝，而纯文字输入的字数校验维持原状
- [x] 3.3 网址抽取失败时抛出用户可见错误（复用 `INVALID_INPUT` + 专用文案），且不写入任何数据；验证：API 单测断言错误码、文案与数据库无新增记录
- [x] 3.4 关键词检索失败静默降级：无 Key / 超时 / 429 / 432 / 433 / 网络不可达时照常生成；验证：单测逐一注入这些失败场景，断言生成仍然成功且日志包含降级记录

## 4. 生成链路接入

- [x] 4.1 改造 `backend/app/services/prompts.py`：大纲与出题模板支持可选的「参考资料」段与对应硬约束（只依据资料、不得越出资料、资料未覆盖时不要编造）；验证：单测断言有资料 / 无资料两种情况下渲染出的提示词结构正确
- [x] 4.2 在大纲调用的结构化输出中增加「是否需要外部资料 + 检索关键词」字段；验证：单测分别覆盖「需要检索」与「不需要检索」两条分支，断言字段被正确解析
- [x] 4.3 大纲生成接入按需检索：判定需要时先检索、再带资料重跑大纲；无可用资料时在生成结果文本中加「未联网核实」标注；验证：单测断言有资料时不出现标注、无资料时出现标注
- [x] 4.4 出题生成接入参考资料；验证：单测断言题目基于资料生成，且既有的「15 题 / 3 关 / 每知识点至少 1 题 / 致命缺陷拦截」校验全部照旧生效
- [x] 4.5 增加检索调用日志与每日检索上限：记录参数、结果条数、credits、耗时与来源网址；达到上限后不再检索；验证：单测断言达到上限后不再发起检索，且日志字段包含 credits 与来源网址

## 5. 回归与真实冒烟

- [x] 5.1 全量后端回归：`pytest` 全绿且核心模块覆盖率 ≥85%；验证：`.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing` 通过
- [x] 5.2 真实冒烟（新知识）：用「Harness Engineering」这类模型训练数据里没有的知识，跑通「输入 → 大纲 → 出题」；验证：连续 3 次无 JSON 解析失败、无致命质量问题，大纲主题不再被误判到别的领域，并记录本次消耗的 credits 与耗时
- [ ] 5.3 真实冒烟（网址输入）：用一个真实网页链接跑通「网址 → 抽取正文 → 大纲 → 出题」；验证：正文抽取成功、生成结果中不出现「未联网核实」标注，并记录知识源实际长度
- [x] 5.4 回滚验证：把 `SEARCH_MODE` 设为 `off` 重跑同一份输入；验证：行为与改动前一致（提示词中不含参考资料段），确认可一键回退
