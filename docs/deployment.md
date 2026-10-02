# 本地与线上配置 / Local and online profiles

两个配置文件只选择运行环境、数据库和网络入口。游戏引擎、玩家账号、存档、世界书与 Agent 调用使用同一套代码。

## 本地 / Local

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[agents,portal]"
.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --profile local --catalog config\games.example.json --db game.sqlite3
```

本地配置是 `config/local.json`。API 仅绑定 `127.0.0.1`，SQLite 文件包含账号、存档与事件。旧版 SQLite 表在启动时原位迁移并保留数据；迁移前建议备份数据库文件。前端在另一个终端运行 `cd web && npm install && npm run dev`，访问 `http://127.0.0.1:5173`。

## 线上 / Online

安装 `.[agents,portal,online]`。将以下变量交给部署平台的密钥管理；不要写入配置文件或仓库：

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@DB_HOST:5432/story
STORY_BAILIAN_API_KEY=<model key>
STORY_ALLOWED_HOSTS=game.example.com
STORY_ALLOWED_ORIGINS=https://app.example.com
STORY_CATALOG=/srv/story/config/games.json
```

在容器或虚拟环境中启动：

```sh
python -m story_harness.cli.portal_api --profile online --port 8765
```

线上配置是 `config/online.json`。服务绑定 `0.0.0.0`，请求 Host 必须匹配 `STORY_ALLOWED_HOSTS`；登录与写入请求的 Origin 必须匹配 `STORY_ALLOWED_ORIGINS`。在 `web/` 运行 `npm ci && npm run build`，将 `dist/` 作为静态站点部署。浏览器与 API 使用同一 HTTPS 来源，由反向代理将 `/v1` 路由到 API。网页认证使用 `Secure`、`HttpOnly`、`SameSite=Lax` Cookie，不向 JavaScript 返回会话令牌；本地 CLI 仍可使用 Bearer 令牌。服务启动时自动执行 Alembic 迁移，PostgreSQL 迁移通过 advisory lock 串行化。

当前线上运行建议单个 API worker。单个游戏的并发回合与跨实例调度锁尚未实现；数据库乐观版本校验会拒绝冲突提交。Redis 可以在后续作为活跃会话缓存加入，不承担存档权威数据。

玩家画像独立于 AgentScope 的回合上下文。`player_memory.driver` 可选 `none` 或 `mem0`；线上还需 `STORY_PLAYER_MEMORY_ENABLED=1` 才采集和提炼画像，默认 `0`。Mem0 开源库使用本机持久化 Qdrant，不需要阿里云对象存储；玩家需在画像页面单独开启。每 6 条有效输入且至少间隔 12 小时批量提炼，模型和向量调用由平台承担，不扣玩家积分；关闭或百炼故障不会阻断故事回合。部署单 API worker；若扩为多副本，需要共享向量存储及分布式任务领取机制。本地配置默认不加载 Mem0；如要试用，安装 `.[player-memory]`、将 `config/local.json` 的驱动改为 `mem0`，并提供支持 `text-embedding-v4` 的百炼按量付费 Key 与对应地域 Base URL。

按量付费 ECS 的单机 Docker Compose 部署清单见 [`deploy/ecs/README.md`](../deploy/ecs/README.md)。该配置使用公开代码镜像、独立挂载的私有剧本目录和 PostgreSQL 数据盘；线上百炼配置使用按量付费接口。

## 模型连接容错

部署环境必须能通过 HTTPS 访问配置中 `models.base_url` 的主机，并正确注入模型密钥。`/health` 只检查 API 进程是否存活，不代表外部模型可用；发布后应从部署环境发起一次实际的短模型请求验证连通性。

`models.connect_timeout_seconds`、`models.timeout_seconds`、`models.max_retries` 分别控制连接超时、响应超时和 SDK 对临时故障的重试次数。示例配置为 10 秒、90 秒、2 次重试。连接失败、响应超时、限流和上游 5xx 会返回可重试提示；前端的“重试这条行动”复用原 `request_id`。只有成功完成的回合会结算积分，同一请求不会重复扣费。持续断网或上游长期不可用仍需恢复网络或切换已配置的模型服务，不能靠重试消除。

## English summary

Install `.[agents,portal,online]`, provide `DATABASE_URL`, `STORY_BAILIAN_API_KEY`, `STORY_ALLOWED_HOSTS`, and `STORY_CATALOG` as deployment environment variables, then run `python -m story_harness.cli.portal_api --profile online`. `STORY_ALLOWED_ORIGINS` is needed for browser clients. The online API uses PostgreSQL, automatic Alembic migrations, and the same repository implementations as local SQLite. Run one API worker until distributed turn coordination is added.

The deployment needs outbound HTTPS access to `models.base_url`. `/health` is a process liveness check, so verify model connectivity with a short real request after deployment. Model connection/response timeouts and retry count are configurable in the `models` section. Retrying a failed turn with its original request ID does not duplicate the game action or credit charge.
