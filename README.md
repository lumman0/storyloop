# NPC World Agent Harness

[中文](README.md) · [English](README.en.md)

一个本地运行的 AI 文游 harness。主控与 NPC 使用独立的 AgentScope ReAct 上下文；世界状态以事件为准，角色只接收自己能观察到的信息。当前提供命令行玩家入口和仅监听本机的 FastAPI 接口，没有网页前端。

## 已实现

- 剧本包：角色卡、带可见范围的 JSON 世界书、初始状态和预设行动。
- 游戏循环：玩家输入、主控决策、NPC 回复、环境事件、主线日程与分支结局；每轮有独立的下一步建议。
- 玩家入口：注册、登录、选择游戏、保存和继续游戏。状态与存档使用 SQLite。
- 可观测性：可选的 Langfuse trace、session 和指标；模型及回合预算可通过配置文件调整。

仓库中的 `examples/freeform` 和 `examples/scheduled` 是公开的合成示例。私人剧本和模型密钥不包含在仓库中。

## 快速开始

需要 Python 3.12 或更新版本。在仓库根目录执行以下命令，适用于 Windows CMD 和 PowerShell：

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[agents,portal]"
```

先运行不需要模型密钥的离线示例：

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.interaction_demo examples\freeform
```

要使用真实模型游玩公开的港口剧本，启动玩家入口：

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_play --catalog config\games.example.json --db game.sqlite3
```

首次启动会提示注册或登录；开始游戏时会隐藏读取模型 API Key。默认模型配置是 [`config/bailian-token-plan.json`](config/bailian-token-plan.json)，也可以通过 `--config` 指定其他配置。Windows 上，目录设置、密钥和有效的登录会在本机保存。之后可直接运行：

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_play
```

如果需要 HTTP API，可运行 `.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --catalog config\games.example.json --db game.sqlite3`，再访问 `http://127.0.0.1:8765/docs`。要接入 Langfuse，安装 `.[agents,portal,observability]` 并配置相应环境变量。

在 macOS/Linux 上，用 `python3.12` 创建虚拟环境，并将上述 Python 路径换成 `.venv/bin/python`、剧本路径分隔符换成 `/`。
