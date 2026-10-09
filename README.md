# StoryLoop Platform

[中文](README.md) · [English](README.en.md)

StoryLoop Platform 是面向 AI 互动叙事的玩家与创作者平台，提供剧本管理、单人存档、账号、积分结算和网页体验。叙事生成与事件执行通过独立的 [StoryLoop Harness](https://github.com/storyloop0/storyloop-harness) 公共接口接入。

当前普通回合采用 `single_call`：分别投影玩家和相关 NPC 可见的历史与经历，组合场景上下文，由共享场景模型一次返回结构化提议，再由后端校验、提交事件并更新状态与观察。角色上下文是身份、经历与信息视角的数据；每个 NPC 不对应一个独立运行的 ReAct 实例。

## 当前能力

| 能力 | 实现范围 |
| --- | --- |
| 互动叙事 | 自由输入、角色回应、行动建议、交互与小说展示模式；支持剧情节点和故事时间推进。 |
| 剧本内容 | 版本化剧本包、角色卡、初始状态、声明式状态字段、开场及按可见范围筛选的 JSON 世界书。公开示例位于 `examples/`。 |
| 玩家体验 | React 前端与 FastAPI API；注册登录、目录、私有剧本上传、创建和续玩单人存档、历史记录、SSE 回合进度与故事片段。 |
| 内容管理 | 作者送审不可变版本、审核员隔离试玩、管理员管理账号与角色、公开版本、邀请码和操作审计。 |
| 存储与结算 | SQLAlchemy 支持本地 SQLite 和线上 PostgreSQL；保存事件、观察、状态、待办工作与账务。请求 ID 支持回合重试和结算恢复。 |
| 可选集成 | OpenAI 兼容模型接口、Langfuse 追踪，以及经玩家授权的 Mem0 偏好提炼。玩家画像与游戏事实、NPC 经历分离。 |

## 架构与边界

```text
React / Vite → FastAPI 平台 → StoryLoop Harness
                    ↓          上下文投影 → 生成 → 校验 → 提交
              SQL 存档与账务
```

平台负责鉴权、内容生命周期、模型适配、持久化、计费和部署；harness 负责可复用的叙事运行契约。当前依赖范围为 `storyloop-harness>=0.2,<0.3`，`pyproject.toml` 固定源码提交 `cb2be84dad44cbfc6e18d16eebc071c2234f7b22`。`scripts/build_harness.py` 从该提交构建 wheel；下方安装命令显式使用这个产物。

共享场景模型会看到多个角色的上下文，视角投影和行为约束不构成角色之间的硬信息隔离。长局上下文从已提交历史中选择近期与相关经历，原始事件保留；当前世界书使用 JSON 条目检索。普通回合的一次场景生成也不代表开场、行动建议或其他功能都只调用一次模型。

项目仍在孵化，API、配置和存储格式可直接调整，不承诺向后兼容。当前唯一回合引擎为 `single_call`；包含旧 `npc_reply` 待办的存档会被拒绝，应重新创建存档。

## 快速开始

需要 Python 3.12+、Node.js 24 和 Git。以下 PowerShell 命令在仓库根目录执行，使用本仓库独立虚拟环境。首次构建使用空的 `dist/harness` 输出目录。

```powershell
py -3.12 -m venv .venv
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe scripts/build_harness.py --out-dir dist/harness
.\.venv\Scripts\python.exe -m pip install dist/harness/storyloop_harness-0.2.0-py3-none-any.whl -e ".[agents,portal]"
.\.venv\Scripts\python.exe scripts/check_environment.py --config config/local.json
```

环境检查应指向本仓库的解释器与源码；它检查导入位置和配置存储驱动，不验证数据库或模型连通性。

真实游玩需要模型密钥。下面通过环境变量提供密钥并启动本地 API：

```powershell
$env:STORY_BAILIAN_API_KEY = "your-api-key"
.\.venv\Scripts\python.exe -m storyloop_platform.cli.portal_api --catalog config/games.example.json --config config/local.json --db game.sqlite3
```

也可将 `config/application.local.example.json` 复制为被 Git 忽略的 `config/application.local.json`，填写 `models.api_key`；`config/local.json` 会相对于自身目录读取此文件，非空的 `STORY_BAILIAN_API_KEY` 优先。当前本地配置指定百炼香港 OpenAI 兼容端点与 `deepseek-v4.1-flash`；如使用其他服务，调整配置中的端点、任务模型与计费设置。Windows 本地 CLI 在缺少密钥时可交互询问并通过 DPAPI 保存。

另开终端启动前端：

```powershell
cd web
npm ci
npm run dev
```

访问 [本地前端](http://127.0.0.1:5173) 注册、创建存档并游玩。Vite 将 `/v1` 代理到 `127.0.0.1:8765`，API 文档位于 [本地 API /docs](http://127.0.0.1:8765/docs)。本地默认使用 SQLite，玩家画像默认关闭。

macOS/Linux 用 `python3.12 -m venv .venv` 创建环境，将 Python 路径替换为 `.venv/bin/python`；环境变量使用 `export STORY_BAILIAN_API_KEY="your-api-key"`，清除导入覆盖使用 `unset PYTHONPATH`。其余 CLI 参数和 npm 命令相同。

## 开发与验证

安装全部测试相关集成及 CI 使用的 uv 版本，然后运行后端离线回归。wheel 安装测试会调用 `uv`、构建固定 harness 提交并创建临时环境，因此首次运行仍可能需要网络下载依赖。

```powershell
.\.venv\Scripts\python.exe -m pip install uv==0.11.25 dist/harness/storyloop_harness-0.2.0-py3-none-any.whl -e ".[agents,portal,observability,player-memory,online,test]"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
$env:STORY_BAILIAN_API_KEY = "offline-test"
$env:LANGFUSE_PUBLIC_KEY = ""
$env:LANGFUSE_SECRET_KEY = ""
.\.venv\Scripts\python.exe -m pytest tests -q
cd web
npm ci
npm test
npm run build
```

浏览器回归另运行 `npx playwright install chromium` 与 `npm run test:e2e`，使用模拟 API。CI 在 Windows/Linux 使用 Python 3.12 验证后端，并在 Linux 使用 Node.js 24 验证前端与浏览器。测试中的 `offline-test` 不是可用于真实游玩的密钥。

```text
src/storyloop_platform/  API、SQL、配置、模型适配、计费和 CLI
web/                    React / Vite 前端
config/                 运行配置与剧本目录示例
examples/               合成剧本包
tests/                  后端与独立安装回归
deploy/ecs/             Docker Compose 部署资源
```

## 限制与后续方向

离线功能测试不证明真实模型叙事质量、角色信息约束效果或生产环境的恢复能力；真实模型、PostgreSQL 和部署环境需单独验证。当前建议使用单个 API worker；结算快照支持已完成回合的恢复，但尚无完整的逐模型调用日志，也不保证跨进程或多 worker 恢复。当前上下文选择也会受窗口预算影响。

后续可探索上下文来源、选择原因与预算明细，长局记忆策略，叙事质量与成本对照，以及更多故障恢复案例。这些是未来方向，尚不作为已有能力承诺。

## 许可证

本项目采用 [MIT License](LICENSE)。StoryLoop Harness 同样采用 MIT。
