# ECS Docker Compose 部署

这个部署将网站、API 和 PostgreSQL 放在一台按量付费 Linux ECS 上。公开仓库只包含程序；私有剧本和密钥分别放在服务器的私有目录和 `.env` 中。当前方案使用单个 API worker。

## 服务器准备

1. 在安全组入方向放通 TCP 80、443；SSH 22 只允许管理员公网 IP。应用无需对公网开放 8765、5432、5173。
2. 安装 Docker Engine 和 Compose 插件。确认 `docker compose version` 可运行。
3. 创建 `/srv/storyloop-data`。只有系统盘时，该目录可暂时放在系统盘上；应定期将数据库备份复制到 ECS 以外。以后增加数据盘时，先用 `lsblk -f` 核对设备，再将数据迁移到挂载点并设置开机自动挂载；不要假定设备名。
4. 将私有剧本放在 `/srv/storyloop-private`。目录内需要 `catalog.json` 和其中引用的剧本包，例如 `winter-show/`。剧本包路径相对于 `catalog.json`，不需要复制进公开仓库。当前本地可使用 `D:\ai\romance-validation-private\catalog.json` 与同目录的 `winter-show/`；旧版 `portal-catalog.json` 含指向本机其他目录的条目，不能直接用于容器。

官方剧本仍由本地只读挂载提供。用户上传剧本写入 `/srv/storyloop-data/uploads`，作者与版本元数据写入 PostgreSQL；上传包不会写入官方目录。备份数据库时，也要备份 `/srv/storyloop-private` 和 `/srv/storyloop-data/uploads`，保持数据库记录与发布包版本一致。后期可将用户发布包迁往私有 OSS。

## 配置与启动

在 ECS 上克隆仓库，然后进入 `deploy/ecs`：

```sh
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

- `POSTGRES_PASSWORD` 使用 URL 安全的随机字符串，例如 `openssl rand -hex 32` 的输出。数据库首次初始化后，不能只修改此值来轮换已有数据库密码。
- `STORY_BAILIAN_API_KEY` 使用百炼**按量付费** API Key。`STORY_BAILIAN_BASE_URL` 必须与 Key 所属地域一致；当前 ECS 示例使用中国香港的 `https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1`。Token Plan 个人版 Key 不用于公开应用后端。
- `STORY_ALLOWED_HOSTS` 填玩家访问的 IP 或域名，不含协议和端口；`STORY_ALLOWED_ORIGINS` 填浏览器完整来源，例如 `https://47.76.236.125`。切换域名时同步修改两项。
- `STORY_DATA_DIR` 和 `STORY_PRIVATE_DIR` 填前面准备的绝对路径。

先检查私有剧本与数据目录，再启动：

```sh
test -f /srv/storyloop-private/catalog.json
test -d /srv/storyloop-data
docker compose config -q
docker compose up -d --build
docker compose ps
curl -fsS -H 'Host: <ECS 公网 IP>' http://127.0.0.1/health
```

线上注册需要一次性邀请码。首次启动后，在 `deploy/ecs` 目录执行下面的命令生成邀请码，再通过安全渠道交给内测玩家。每个邀请码只能注册一个账号，默认 30 天有效；登录不需要邀请码。

```sh
docker compose exec api python -m story_harness.cli.signup_invite --count 5
```

Nginx 对注册、登录和创建存档入口设置了按来源 IP 的请求速率限制。一个玩家账号的回合在单 API worker 内串行处理，避免多个存档同时通过同一笔余额检查。

网页登录使用 7 天有效的 `Secure`、`HttpOnly`、`SameSite=Lax` 会话 Cookie；后端数据库只保存令牌哈希。登录和写入请求必须来自配置的 HTTPS Origin。部署认证方式切换后，已有浏览器标签页需要重新登录一次，存档不会丢失。本地 CLI 仍支持 Bearer 令牌。

浏览器入口为 `https://47.76.236.125/`，HTTP 自动跳转 HTTPS。Nginx 使用 Let's Encrypt 的公网 IP 证书，证书约 6 天到期，必须保持自动续期。首次部署前，先使用仅含 ACME 挑战路径的 HTTP 配置签发证书，再启用 443 配置；证书目录为 `/srv/storyloop-data/letsencrypt`。服务器安装并启用续期计时器：

```sh
cp storyloop-cert-renew.service /etc/systemd/system/
cp storyloop-cert-renew.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now storyloop-cert-renew.timer
systemctl start storyloop-cert-renew.service
```

续期服务使用 Certbot 容器与 ACME webroot，成功检查后重新加载 Nginx。`/v1` 由 Nginx 转发到 API；SSE 流式响应禁用代理缓冲。API 和 PostgreSQL 不发布公网端口。后续换域名时需更新证书路径、Allowed Hosts 与 Allowed Origins。

## 数据与停机

PostgreSQL 数据位于 `/srv/storyloop-data/postgres`。定期执行数据库备份，并将备份存放在 ECS 云盘以外的位置；云盘快照可作为额外恢复手段。停止 ECS 前，先等待正在执行的游戏回合结束。按量付费 ECS 只有选择**节省停机模式**才停止计算资源计费，云盘及保留的 EIP 仍计费；再次开机后 `restart: unless-stopped` 会启动容器。

可用 `docker compose logs --tail=100 api` 查看后端日志。`/health` 仅表示 API 进程可用，正式验证还需要登录并完成一次短回合，检查百炼调用、存档和积分结算。
