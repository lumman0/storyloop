# 本地与线上配置 / Local and online profiles

两个配置文件只选择运行环境、数据库和网络入口。游戏引擎、玩家账号、存档、世界书与 Agent 调用使用同一套代码。

## 本地 / Local

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[agents,portal]"
.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --profile local --catalog config\games.example.json --db game.sqlite3
```

本地配置是 `config/local.json`。API 仅绑定 `127.0.0.1`，SQLite 文件包含账号、存档与事件。旧版 SQLite 表在启动时原位迁移并保留数据；迁移前建议备份数据库文件。

## 线上 / Online

安装 `.[agents,portal,online]`。将以下变量交给部署平台的密钥管理；不要写入配置文件或仓库：

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@DB_HOST:5432/story
STORY_BAILIAN_API_KEY=<model key>
STORY_ALLOWED_HOSTS=game.example.com
STORY_ALLOWED_ORIGINS=https://game.example.com
STORY_CATALOG=/srv/story/config/games.json
```

在容器或虚拟环境中启动：

```sh
python -m story_harness.cli.portal_api --profile online --port 8765
```

线上配置是 `config/online.json`。服务绑定 `0.0.0.0`，请求 Host 必须匹配 `STORY_ALLOWED_HOSTS`；带 Origin 的请求必须匹配 `STORY_ALLOWED_ORIGINS`。没有浏览器前端时，`STORY_ALLOWED_ORIGINS` 可以留空。外部流量应由 HTTPS 反向代理接入；代理转发原始 Host。服务启动时自动执行 Alembic 迁移，PostgreSQL 迁移通过 advisory lock 串行化。

当前线上运行建议单个 API worker。单个游戏的并发回合与跨实例调度锁尚未实现；数据库乐观版本校验会拒绝冲突提交。Redis 可以在后续作为活跃会话缓存加入，不承担存档权威数据。

## English summary

Install `.[agents,portal,online]`, provide `DATABASE_URL`, `STORY_BAILIAN_API_KEY`, `STORY_ALLOWED_HOSTS`, and `STORY_CATALOG` as deployment environment variables, then run `python -m story_harness.cli.portal_api --profile online`. `STORY_ALLOWED_ORIGINS` is needed for browser clients. The online API uses PostgreSQL, automatic Alembic migrations, and the same repository implementations as local SQLite. Run one API worker until distributed turn coordination is added.
