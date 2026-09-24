# OpenSpec 傻瓜教程（给本项目用）

> 目标：读完这一页，你会用 OpenSpec 给项目加功能，不返工。

## 0. 先花 30 秒搞懂它是什么

OpenSpec 不写代码，它是「动手前先把需求写成文档」的流程工具。

平时你的做法：跟 AI 说「帮我加个功能」→ AI 自己猜 → 猜歪了 → 返工。

用 OpenSpec 的做法：

```
AI 先把「要做什么」写成文档  →  你看一眼说 OK  →  AI 才开始写代码
```

就这么简单。它管的是**对齐需求**，代码还是 AI 写。

## 1. 安装（一辈子只做一次）

前提：电脑上有 Node.js，且版本 >= 20.19.0。

打开终端，逐个执行：

```bash
node -v
```

如果版本低于 20.19.0，先去 nodejs.org 装新版。

```bash
npm install -g @fission-ai/openspec@latest
openspec --version
```

能看到版本号 = 装好了。

## 2. 在项目里初始化（一个项目只做一次）

```bash
cd E:\CodexProjects\ai-learn-mini
openspec init
```

它会做两件事：

1. 在项目里生成 `openspec/` 目录
2. 给你的 AI 工具（Claude Code / Cursor 等）装上专属指令

> 如果它弹菜单问「要给哪个 AI 工具装指令」，按提示选就行，不确定就全选。

初始化完，打开 `openspec/` 看一眼，不用背，看一眼就懂了：

```
openspec/
├── specs/            已经做完的、现在生效的功能说明（一开始是空的）
└── changes/          正在进行的改动
    └── archive/      做完的改动，归档扔这儿
```

一句话：**specs = 现在有什么，changes = 现在要改什么。**

## 3. 日常干活：四步循环（记住这个就够用了）

### 第 1 步：想清楚（可选）

在 AI 对话框里输入：

```
/opsx:explore
```

AI 会问你到底想干嘛，然后给你几个方案让你选。需求还不清楚的时候，用这一步特别省事。

你要做的：回答问题，选一个方向。

### 第 2 步：让 AI 出方案

```
/opsx:propose add-checkin
```

（`add-checkin` 是这次改动的名字，随便起，英文小写加横线最好。）

AI 会在 `openspec/changes/add-checkin/` 下写好几份 markdown：

| 文件 | 内容 |
| --- | --- |
| `proposal.md` | 为什么要做、要改什么、会影响哪些地方 |
| `specs/**` | 具体要做成什么样（每条要求 + 验收场景） |
| `design.md` | 技术方案（可选，复杂改动才有） |
| `tasks.md` | 要做的事，一条一条的勾选清单 |

这一步一行业务代码都不会写，全是文档。

### 第 3 步：你审方案（最关键的一步）

打开 `proposal.md` 和 `tasks.md` 看一遍，重点看三件事：

1. 为什么做 —— 是不是你想要的？
2. 要改什么 —— 有没有多改、少改？
3. 影响范围 —— 会不会碰到不该碰的地方？

不满意就直接改 markdown，或者跟 AI 说「第 2 条不要，改成 XXX」。

> 宁可在这里改 10 分钟，也别等代码写完再返工 2 小时。

### 第 4 步：开做

```
/opsx:apply
```

AI 按 `tasks.md` 一条条实现，做完一条勾掉一条。

你要做的：盯着点，让它一条条来，别一口气糊一大堆。

### 第 5 步：收工归档

```bash
openspec validate add-checkin    # 检查文档格式对不对
openspec archive add-checkin     # 归档
```

归档后会发生两件事：

- 这次改动被移到 `openspec/changes/archive/2026-09-22-add-checkin/`
- 新的功能说明被合并进 `openspec/specs/`

于是下次 AI 干活前读 `specs/`，就知道这个项目现在到底长什么样了。

## 4. 在 Codex 里怎么用（重点，别跳过）

`/opsx:propose` 这种斜杠命令是给 Claude Code、Cursor 那类 IDE 助手准备的。
**Codex 里没有斜杠命令，用下面两种办法，效果一样。**

### 办法 A：用命令行 + 让 Codex 读文件（最稳）

终端里你自己跑 `openspec` 命令，然后把改动目录告诉 Codex：

```
读一下 openspec/changes/add-checkin/ 里的 proposal.md 和 tasks.md，
按 tasks.md 一条条实现，做完勾掉。
```

### 办法 B：直接复制这段「万能开场白」发给 Codex

```
请用 OpenSpec 流程帮我扩展功能：

1. 先读 openspec/ 目录，了解项目现有的 specs
2. 我说完需求后，你在 openspec/changes/<change-name>/ 下写：
   proposal.md、specs/、tasks.md（复杂的话加 design.md）
3. 写完先停下，等我确认，不要动任何业务代码
4. 我确认后，再按 tasks.md 逐条实现，做一条勾一条
5. 全部做完，跑 openspec validate，再跑 openspec archive 归档

我的需求是：<在这里写你要加的功能>
```

里面最关键的一句是「写完先停下，等我确认」。没有这句，AI 就会一路写到底，OpenSpec 就白用了。

## 5. 完整走一遍（真实例子）

假设要给项目加一个「学习打卡」功能。

```bash
openspec list
```

输出是空的，说明现在没有进行中的改动。

然后：

1. 把第 4 节那段开场白发出去，需求写「加学习打卡，每天能打卡一次，能看到连续打卡天数」
2. AI 生成 `openspec/changes/add-checkin/`，里面是 proposal / specs / tasks
3. 你读 proposal：
   - 为什么做：提升用户留存（对）
   - 要改什么：新增打卡页、后端打卡接口、打卡记录表（对）
   - 影响范围：前台首页 + 后端 API（对）
   - 一看不对就直接改文档
4. 满意了跟 AI 说「确认，开始做」
5. AI 按 tasks.md 一条条写代码，勾任务
6. 收尾：

```bash
openspec validate add-checkin
openspec archive add-checkin
```

完成。整个过程的产物你随时能翻出来看，谁改的、为什么改，一目了然。

## 6. 常用命令（就这 6 个，够用了）

| 命令 | 干嘛的 |
| --- | --- |
| `openspec init` | 初始化，一个项目做一次 |
| `openspec update` | 升级 CLI 后刷新 AI 指令，跑一次就行 |
| `openspec list` | 看现在有哪些改动在进行 |
| `openspec show <名字>` | 看某个改动的详情 |
| `openspec validate <名字>` | 检查文档格式对不对 |
| `openspec archive <名字>` | 做完了归档（加 `--yes` 跳过确认） |

## 7. 别踩的坑

- 一次只做一件事：一个 change 只解决一个功能，别把「打卡 + 排行榜 + 商城」塞进同一个。
- 改需求就改 markdown：需求变了，让 AI 改 `proposal.md` / `tasks.md`，别直接让它改代码。
- 前后端一起改：放同一个 change 里，在 `tasks.md` 里分成「前端 / 后端」两组，别开两个 change。
- 哪些事别走流程：改文案、修个明显 bug、调样式，直接让 AI 干就行。OpenSpec 是给「要思考的新功能」用的，不是给所有事都套流程。
- 写得太长没人看：proposal 一屏能看完最好。写三页没人读的文档，不如写半页大家都看的。
