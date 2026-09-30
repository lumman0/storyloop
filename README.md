# NPC World Agent Harness

[中文](README.md) · [English](README.en.md)

一个 AI 文游 harness 与浏览器玩家入口。主控与 NPC 使用独立的 AgentScope ReAct 上下文；世界状态以事件为准，角色只接收自己能观察到的信息。React 前端位于 `web/`，通过 FastAPI 接口与游戏服务通信。

## 已实现

- 剧本包：角色卡、带可见范围的 JSON 世界书、初始状态和预设行动。
- 游戏循环：玩家输入、主控决策、NPC 回复、环境事件、主线日程与分支结局；每轮有独立的下一步建议。
- 玩家入口：注册、登录、选择游戏、保存和继续游戏。相同的存储接口可使用本地 SQLite 或线上 PostgreSQL。
- 浏览器界面：剧本大厅、个人存档、可恢复的游玩记录，以及独立显示的下一步建议。
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

要使用真实模型在浏览器里游玩，先启动 API。模型密钥须已保存在本机玩家入口设置中，或设置 `STORY_BAILIAN_API_KEY` 环境变量：

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --catalog config\games.example.json --db game.sqlite3
```

另开一个终端，启动独立前端：

```cmd
cd web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`，注册账号、创建存档并游玩。前端需要 Node.js 20.19+；本地 Vite 自动将 `/v1` 转发到 `127.0.0.1:8765`。不想使用网页时，仍可运行 `portal_play` 命令行入口；它会在开始游戏时隐藏读取模型 API Key，并在 Windows 本机保存设置。API 文档位于 `http://127.0.0.1:8765/docs`。要接入 Langfuse，安装 `.[agents,portal,observability]` 并配置相应环境变量。

在 macOS/Linux 上，用 `python3.12` 创建虚拟环境，并将上述 Python 路径换成 `.venv/bin/python`、剧本路径分隔符换成 `/`。

线上使用同一套 API 和数据仓储，安装 `.[agents,portal,online]` 后以 `--profile online` 启动，配置见 [线上部署说明](docs/deployment.md)。旧 SQLite 存档在首次启动时由 Alembic 自动迁移。
