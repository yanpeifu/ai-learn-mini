# BUG 修复记录

> 覆盖 2026-09-17 ~ 2026-09-20 的开发与联调过程。**现象 → 原因 → 解决**，按类别分组。

## 一、环境与构建

| # | 现象 | 原因 | 解决 |
| --- | --- | --- | --- |
| 1 | AI 依赖（pydantic-core 等）在 Python 3.14 装不上 | 3.14 的预编译轮子尚不稳定 | 用 `uv` 装独立 Python 3.12 建 `.venv` |
| 2 | `pytest` 卡住不返回、CPU 占满 | 沙箱禁止 Python 进程在项目目录新建文件，`.pytest_cache` 写入被拒 | `pyproject.toml` 的 addopts 加 `-p no:cacheprovider` |
| 3 | `alembic` 报 UnicodeDecodeError | `alembic.ini` 被用系统编码（GBK）读取 | 该文件保持纯 ASCII，中文注释移到别处 |
| 4 | 迁移执行报 `NameError: app / Text` | autogenerate 生成的脚本缺 import | 补 `import app.db.types` 与 `from sqlalchemy import Text` |
| 5 | `pnpm install` 报 `ERR_PNPM_IGNORED_BUILDS` | pnpm 11 默认拦截依赖构建脚本 | `pnpm approve-builds --all` + `pnpm-workspace.yaml` 白名单 |
| 6 | Taro 脚手架拒绝 `--npm pnpm` / `--css sass` | CLI 枚举不接受这些值 | 去掉这两个参数，改为交互式选择 |
| 7 | `tsc` 报 webpack-chain / webpack 类型错误 | 第三方类型声明与 webpack 5.91 不兼容 | `tsconfig.json` 加 `skipLibCheck: true` |
| 8 | `tsc` 报 TS6198 未使用参数 | config/index.ts 解构了没用的参数 | 改为 `async (merge) =>` |
| 9 | 手写脚手架与官方模板不一致 | 自行拼装容易缺文件 | 改用官方 `taro init` 生成 |
| 10 | 重命名 frontend 目录后依赖全失效 | pnpm 的 junction 存的是绝对路径 | 目录名固定，别在装依赖后改名 |
| 11 | `corepack enable` 报 EPERM | 要写入受保护的 `D:\Program Files\NodeJs` | 用 `npx pnpm@11`，或把 prefix 设到 `E:\nodejs-global` 后加 PATH |
| 12 | 命令行提示找不到 `pnpm` | 装了 pnpm 但目录不在 PATH | 把全局目录加入用户 PATH 并**重开窗口** |

## 二、前后端联调

| # | 现象 | 原因 | 解决 |
| --- | --- | --- | --- |
| 13 | H5 预览白屏，控制台 `process is not defined` | 代码里直接用 `process.env.X`，H5 运行时没有 process 对象 | `config/index.ts` 用 `defineConstants` 构建期写死后端地址 |
| 14 | `app.ts` 报「Unterminated regular expression」 | `.ts` 文件里写了 JSX | 改名为 `app.tsx` |
| 15 | 上传代码失败：`invalid file: SyntaxError` | `project.config.json` 的 es6/enhance 为 false，且 browserslist 目标是「支持 ES6 模块」，产物保留了模板字符串/箭头函数 | es6、enhance 置 true；browserslist 改为 `ios >= 9 / android >= 5` |
| 16 | 改了 `.env.development` 不生效 | `build:weapp` 按生产模式编译，只读 `.env.production` | 两个 env 文件都写同样的值 |
| 17 | 登录报 503「登录服务暂不可用」 | 模拟器里 `wx.login()` 会返回真 code，而后端没有 AppID/Secret | 前端加 `TARO_APP_DEV_LOGIN=true` 强制发假 code；后端日志写明原因 |
| 18 | 登录 500 `no such table: user` | 只启动了服务，没执行数据库迁移 | 启动前跑 `alembic upgrade head` |
| 19 | 手机/模拟器连接超时 `ERR_CONNECTION_TIMED_OUT` | 电脑局域网 IP 变了（三天变了三次：192.168.2.92 → 192.168.0.222 → 10.129.0.222） | 查当前 IP → 改 `TARO_APP_API_BASE` → 重新编译；建议路由器绑定静态 IP |
| 20 | 浏览器打开 `http://0.0.0.0:8000` 打不开 | `0.0.0.0` 是监听地址，不能作为访问目标 | 本机用 `127.0.0.1`，手机用局域网 IP |
| 21 | H5 页面跨域请求失败 | 后端没配 CORS | 加 `CORSMiddleware`（本地允许 `*`） |
| 22 | 体验版扫码「暂无体验权限」 | 预览码只允许项目成员；体验版只允许体验成员 | 用同微信号扫码预览，或在后台把对方加为体验成员 |
| 23 | 模拟器控制台报 `DOMNodeRemoved`、preload 警告 | 开发者工具自身的 Chromium 兼容问题 | 忽略，与小程序代码无关 |

## 三、后端代码

| # | 现象 | 原因 | 解决 |
| --- | --- | --- | --- |
| 24 | DeepSeek 返回 400「Prompt must contain the word 'json'」 | `json_object` 模式要求提示词里出现 "json" | 适配层自动追加一条带字段结构的 system 提示 |
| 25 | 出题反复整批重试、白花 40 秒 + 0.05 元 | 结构化校验过严：`level_seq` 必须 1–3、`difficulty` 必须 1–5，一题写坏就整份作废 | 改为**单题容错**：逐题校验、坏题丢弃；难度越界夹到 1–5；题型支持中文/别名归一化 |
| 26 | 抓包可拿到未作答题目的正确答案 | `GET /api/attempt/{id}` 对未作答题目也返回 `correct_answer`/`explanation` | 只对「已作答的题」或「已结算的闯关」返回答案与讲解 |
| 27 | token 失效后页面一直提示「登录状态已过期」 | 请求层只清 token、不重登 | 401 时自动重新静默登录一次并重试原请求 |
| 28 | 出题卡住/失败（手机切后台、隧道重置、90 秒超时） | 40 秒的长请求压在 HTTP 请求里，链路一断就白花钱 | 改为**后台任务 + 前端轮询**：提交立即返回 task_id（幂等复用），前端每秒查进度 |
| 29 | 同一人反复举报即可让题目下架 | 阈值按举报条数统计 | 改为按**去重人数**统计，并加人工下线/恢复接口 |
| 30 | 题目并发/重复提交可能重复计分 | 同一题可重复提交 | 提交幂等：重复提交返回首次判定，不覆盖记录 |

## 四、测试与质量校验

| # | 现象 | 原因 | 解决 |
| --- | --- | --- | --- |
| 31 | 测试用「合格题目」被判定为重复题 | 造数据时题干模板化（只差一个数字），相似度检查命中 | 测试数据加唯一后缀；这属于校验器正确工作 |
| 32 | 担心线上校验标准与质检脚本不一致 | 两套实现容易漂移 | 加 parity 测试：同一份数据交两边，坏样例不漏报、干净样例不误报 |
| 33 | 迁移不可回滚 | 手写迁移容易漏 downgrade | 迁移测试覆盖 `upgrade head` 与 `downgrade base` |
| 34 | 日志太技术化、非技术同事看不懂 | 全英文 + 纯字段 | 改为中文可读格式：级别/字段名/用途/错误码全部中文化，消息改成白话（可用 `LOG_FORMAT=json` 切回机器格式） |
| 35 | 5xx/网络错误导致前端直接失败 | 长任务失败没有重试与友好提示 | 统一重试策略：超时/坏格式/网络抖动重试 2 次，401/402/403 立即中止；错误码映射成用户可读文案 |

## 快速自查（连不上时按顺序看）

1. 后端窗口是否有「服务已启动，可以开始使用了」
2. 手机浏览器打开 `http://<当前IP>:8000/api/health` 是否返回 JSON
3. `ipconfig | Select-String IPv4` 的 IP 是否与 `frontend/.env.production` 里一致
4. 是否执行过 `alembic upgrade head`（新库必须）
5. 开发者工具「详情 → 本地设置」是否勾选「不校验合法域名」
