# NPC World Agent Harness

一个纯命令行的互动叙事 harness。世界事实由事件和状态快照管理；观察按接收者投递；主控和每个 NPC 分别运行 AgentScope ReAct，上下文互相隔离。回合调度器按预算处理 NPC 回复和背景事件，支持在玩家聊天时继续推进游戏时间。

此仓库只包含框架代码、测试以及原创的合成验证剧本。`examples/freeform` 展示背景资料型世界书，`examples/scheduled` 展示规则和日程型世界书。它们不依赖任何私人剧本原件。

## 安装

需要 Python 3.12 或更新版本。在 PowerShell 中进入仓库目录：

```powershell
py -3.12 -m venv .venv
& '.venv\Scripts\python.exe' -m pip install -e '.[agents]'
```

## 离线验证

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' -m story_harness.cli.demo_check
```

离线演示使用确定性的模型替身，不发起 API 请求。两个合成剧本也可以分别运行：

```powershell
& '.venv\Scripts\python.exe' -m story_harness.cli.interaction_demo examples\freeform
& '.venv\Scripts\python.exe' -m story_harness.cli.interaction_demo examples\scheduled
```

## 接入模型

[`config/bailian-token-plan.json`](config/bailian-token-plan.json) 将主控、NPC 回复、待办选择和叙述映射到可配置的模型 ID，同时配置接口地址、步数预算和 SQLite 路径。百炼示例将 `tool_choice_policy` 设为 `auto_only`，以兼容 Qwen 不支持强制工具调用的接口；换用支持强制工具调用的模型可设为 `native`。密钥通过配置的 `api_key_env` 指向环境变量，不能写进配置文件或存档。

```powershell
& '.venv\Scripts\python.exe' -m story_harness.cli.react_play examples\freeform --config config\bailian-token-plan.json --db game.sqlite3 --game-id demo
```

缺少环境变量时，终端会隐藏读取 API Key。当前提供 SQLite 存储和进程内 AgentScope memory；PostgreSQL、Redis、轻量模型 NPC 预筛选、通用自由动作裁定及语义 RAG 仍是扩展点。

剧本包可在 `manifest.json` 中设置可选的 `opening` 文本；创建新游戏时，CLI 会在玩家第一次输入前显示它。继续已有 `game-id` 不会重复开场。`examples/freeform` 是原创的港口市集技术验证剧本：玩家位于港口广场，附近有一名码头工，市集在第 4 个时间格开门。它不是私人剧本的改写。

## 多日程游戏

需要主线日程、玩家关键选择和结局判定的剧本可在包目录增加 `campaign.json`，并在 `manifest.json` 的 `initial_state.campaign` 放入对应的初始状态。`CampaignProgram.initial_state(actor_ids)` 可生成该状态。日程步骤按时间格排序，支持场景广播、约会选择、私密留言、嘉宾来信和结局；普通输入继续交给现有主控与 NPC ReAct。背景时间随着聊天前进，遇到关键选择会暂停等待玩家输入。

```powershell
& '.venv\Scripts\python.exe' -m story_harness.cli.campaign_play path\to\scenario --db game.sqlite3 --game-id my-game
```

在终端使用 `/choose 选项ID` 回答选择，留言格式为 `/choose 嘉宾ID 留言内容`；`/next` 推进一个时间格，`/quit` 保留进度并退出。剧本数据可放在仓库外，仓库中不需要包含私人原件。日程调度、选择和来信与 ReAct 回合共用 `GameStore` 事件和同一个 Langfuse Session。

同一 `--db` 与 `--game-id` 会接续进度；若进程在已提交玩家行为、尚未结束回合时中断，启动时会先恢复该回合。带日程的剧本要求 NPC 回复工作耗时为 0 个时间格，玩家输入或 `/next` 负责推进时间，避免后台回复跨过尚未处理的选择。

## Langfuse 链路与指标

Langfuse 是 harness 的可选可观测适配器，适用于实时 ReAct 演示和离线互动演示。安装 `observability` 扩展并设置项目的公钥、密钥和服务地址即可启用；未设置密钥时游戏照常运行，密钥只设置了一半时会明确报错。Windows CMD 示例：

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[agents,observability]"
set LANGFUSE_PUBLIC_KEY=你的公钥
set LANGFUSE_SECRET_KEY=你的密钥
set LANGFUSE_BASE_URL=https://cloud.langfuse.com
.venv\Scripts\python.exe -m story_harness.cli.react_play examples\freeform --db game.sqlite3 --game-id demo
```

在 PowerShell 中使用 `$env:LANGFUSE_PUBLIC_KEY='...'` 形式设置环境变量。`LANGFUSE_BASE_URL` 应改为你的 Langfuse 实例地址。

一轮游戏产生一条 `story-turn` trace，以 `game_id`、`turn_id`、剧本 ID 关联。子步骤包含主控决策、上下文来源、世界书和状态工具、模型 generation、待办选择、NPC 回复、事件效果、观察投递与最终叙述。模型 generation 报告模型名、任务和 token 用量；Langfuse 的 Metrics 面板可聚合调用量、耗时、token 和成本。数值 score `story.turn_success`、`story.work_processed`、`story.work_remaining`、`story.player_observations` 和 `story.narration_fallback` 可用于成功率、剧情节奏与回退率看板。终端每轮会打印 `turn_id` 供检索。

同一剧本和 `game_id` 的回合自动归入一个 Langfuse Session，Session ID 为 `<scenario-id>:<game-id>`；每次玩家输入仍是独立的 trace。离线互动演示也使用相同规则，因此可以在 Sessions 页面连续查看一局中的多个回合。过长或含非 ASCII 字符的 ID 会映射为稳定的哈希 ID，原始 `game_id` 仍保留在 trace metadata 中。此设置只影响新产生的 trace，不会改写旧记录。

多日程游戏另外记录 `campaign-start`、`campaign-turn`、`campaign-step`、`campaign-choice`，并报告当前天数、处理的步骤和嘉宾来信数量。

`main-context` 内的模型文本属于决策过程，不会直接展示给玩家或写成世界事实；该步骤的有效结果是结构化的 `MainDecision`。玩家最终看到已提交的可见观察：NPC 对话保留原文，其他观察由叙述模型组织。主控下一轮从已提交的玩家输入、观察和状态重建上下文，清除上一轮未提交的草稿。

默认只记录结构、计数和 ID。若要在 Langfuse 中检查完整提示词、角色卡、玩家输入、工具结果与模型输出，启动前显式设置 `STORY_TRACE_CONTENT=1`；这些内容会发送到所配置的 Langfuse 项目。离线演示 `python -m story_harness.cli.interaction_demo examples\freeform` 使用同一适配器，无需模型 API Key。退出 CLI 时会 flush 已排队的观测数据。

## 源码分区

| 目录 | 职责 |
| --- | --- |
| `core/` | 事件、状态归约、动作规则和物理观察 |
| `world/` | 剧本包加载与世界书权限查询 |
| `runtime/` | 玩家输入、动态待办、日程和完整回合 |
| `agents/` | 主控、NPC、待办选择的 AgentScope ReAct 实现 |
| `adapters/` | SQLite、模型配置及可选 Langfuse 观测 |
| `cli/` | 终端入口与离线演示 |

世界状态以事件提交为准。NPC 的 memory 只保存其独立对话上下文，不能直接改写权威状态。示例动作必须在剧本包中声明，模型只能选择动作 ID，状态效果由规则校验后生成。
