# StoryLoop Platform

[中文](README.md) · [English](README.en.md)

StoryLoop Platform 是面向 AI 互动叙事的运行时与玩家平台。默认引擎将玩家可见历史、相关 NPC 各自的经历和世界状态组装成一个场景上下文，以一次结构化模型调用生成普通回合；后端校验并提交事件，再分别更新角色认知。原有多 Agent ReAct 引擎保留为可配置的 beta 路径。

## 解决的问题

- **多角色认知一致性**：世界事实、角色所知和玩家所见分别建模。世界状态由已提交事件决定；观察和世界书条目按可见范围投递，避免 NPC 凭空知道其他角色的经历。
- **自由互动与主线节奏并存**：玩家可以交谈、观察和行动；待办任务、剧情事件与故事时间在回合中继续推进。每轮工作量有上限，防止 Agent 之间无限互相触发。
- **长线游玩的可恢复性**：账号、单人存档、事件、观察、回合结果和积分流水持久化。请求 ID 用于回合重试，模型故障后可以恢复同一条行动。
- **可替换的基础设施**：模型路由、存储、可观测性及玩家画像通过配置或接口接入，剧本内容与平台运行时分离。

## 核心能力

| 模块 | 职责 |
| --- | --- |
| 剧本包与世界书 | 版本化的角色卡、初始状态、可变状态字段、可选的特殊行动规则、开场、剧情任务和 JSON 世界书；检索前按玩家或角色的可见权限过滤。 |
| 叙事运行时 | 默认单次模型调用同时提出决策、场景正文、相关 NPC 回应、受限状态变化与三个行动建议；有界任务队列按因果顺序提交角色发言和环境事件。交互模式分开展示角色发言，小说模式统一输出第二人称正文。原多 Agent ReAct 路径可通过配置启用 beta。 |
| 状态与时间 | 事件提交后更新快照，并生成各接收者的观察；日程剧本支持剧情节点与按行动时长流逝的故事时间。剧本可声明玩家可见数值及受限的回合变化。 |
| 玩家平台 | React 前端与 FastAPI API 提供注册登录、剧本目录、私有剧本上传、单人存档、续玩和历史记录；SSE 推送回合阶段与可见故事片段。 |
| 内容治理 | 作者提交不可变剧本版本；审核员查看送审内容并隔离试玩；管理员管理角色、账号、公开版本、内测邀请码与操作审计。 |
| 计费与画像 | 根据成功回合的模型 Token 用量结算积分；可选 Mem0 按玩家选择批量提炼游玩偏好，画像与 NPC 记忆、游戏事实隔离。 |
| 可观测性 | 可选 Langfuse 记录 trace、session 与指标，用于查看一次回合中的模型调用和任务处理链路。 |

## 架构

```mermaid
flowchart LR
    UI[React / Vite] --> API[FastAPI 玩家入口]
    API --> Portal[账号 · 存档 · 计费]
    Portal --> Runtime[游戏会话]
    Runtime --> Context[玩家与各 NPC 的独立上下文投影]
    Context --> Main[单次场景模型调用]
    Runtime --> Queue[有界任务队列]
    Queue --> NPC[NPC 发言与观察投递]
    Queue --> Cues[剧情与环境任务]
    Main --> Book[权限过滤的世界书]
    Runtime --> Store[事件 · 观察 · 快照]
    Store --> SQL[(SQLite / PostgreSQL)]
    Portal -. 玩家授权 .-> Mem0[可选玩家画像]
    Runtime -. trace / metrics .-> Langfuse[可选 Langfuse]
```

普通回合从玩家输入开始：上下文投影器分别读取玩家和相关角色有权知道的历史，场景模型一次返回完整故事回应和结构化提议。普通活动以事件经历保存；需要持久改变的物品或世界状态通过剧本声明的字段校验。发生值得回忆的共同互动时，同一结果可给直接参与的 NPC 留下简短事实记忆。运行时提交事件、生成观察，再按因果顺序处理待办工作。剧本选择与时间推进使用脚本数据；心动留言可在一次模型调用中为多位角色生成各自的短信。调度不依赖固定 Agent 图。通过 `runtime.turn_engine=multi_agent_beta` 可保留旧版逐 Agent 调用流程；网页默认只提供 `single_call`。

权威游戏数据与生成上下文分开保存。`GameStore` 管理事件、观察、快照和待办工作；SQLAlchemy 仓储支持本地 SQLite 与线上 PostgreSQL。默认引擎每轮从完整历史中选取近期事件与较早的相关经历，分别投影到玩家和各 NPC 的上下文，不额外调用模型压缩；旧版 beta 路径仍支持按存档、角色隔离的持久摘要。原始事件不会删除，玩家画像 Mem0 也不参与故事事实。`models.context_windows` 与 `runtime.context_window_tokens` 限制模型输入。世界书使用带可见范围的 JSON 条目检索，目前不是向量 RAG。模型调用通过 OpenAI 兼容接口按任务配置；浏览器会话在线上使用 `Secure`、`HttpOnly` Cookie。

## 项目结构

```text
src/story_harness/
  core/       事件、状态转换、观察与计费契约
  world/      剧本包与世界书
  agents/     主控、NPC、选择器与叙述 Agent
  runtime/    回合调度、剧情、时间和呈现
  adapters/   模型配置、SQL 存储与遥测
  portal/     账号、存档、画像、积分和 HTTP API
  cli/        本地演示与服务入口
web/          React 前端
config/       本地与线上配置示例
examples/     可公开使用的合成剧本包
deploy/ecs/   单机 ECS Docker Compose 部署配置
```

## 快速开始

需要 Python 3.12+ 和 Node.js 20.19+。以下命令适用于 Windows CMD 与 PowerShell，在仓库根目录执行：

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[agents,portal]"
```

先运行无需模型 Key 的离线示例：

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.interaction_demo examples\freeform
```

使用真实模型时，创建本机配置文件，将 `models.api_key` 填为可用的百炼按量付费 Key；该文件被 Git 忽略。`config/local.json` 默认使用香港端点的 `deepseek-v4.1-flash`，Token Plan 个人版请改用专用的 `config/bailian-token-plan.json`。`STORY_BAILIAN_API_KEY` 环境变量会覆盖文件中的 Key。

`config/local.json` 与 `config/online.json` 默认使用 `runtime.turn_engine: "single_call"`。需要对照旧版多 Agent 流程时，可在独立配置副本中改为 `"multi_agent_beta"`；网站不提供玩家切换入口。

```cmd
copy config\application.local.example.json config\application.local.json
.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --catalog config\games.example.json --config config\local.json --db game.sqlite3
```

另开终端启动前端：

```cmd
cd web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173` 注册、创建存档并游玩。Vite 将 `/v1` 代理到本机 API `127.0.0.1:8765`；API 文档位于 `http://127.0.0.1:8765/docs`。macOS/Linux 使用 `python3.12` 创建虚拟环境，并将 Python 路径换为 `.venv/bin/python`。

本地默认使用 SQLite，玩家画像默认关闭。线上配置使用 PostgreSQL；Mem0 可选用 ECS 云盘上的嵌入式 Qdrant 保存玩家偏好，需平台开关和玩家授权同时开启。私有剧本和密钥不放在仓库中。部署、积分规则和剧本包格式分别见[部署说明](docs/deployment.md)、[计费说明](docs/billing.md)与[用户剧本设计](docs/user-scenarios.md)。
