# ECS Docker Compose 部署

这个部署将网站、API 和 PostgreSQL 放在一台按量付费 Linux ECS 上。公开仓库只包含程序；私有剧本和密钥分别放在服务器的私有目录和 `.env` 中。当前方案使用单个 API worker。

## 服务器准备

1. 在安全组入方向放通 TCP 80、443；SSH 22 只允许管理员公网 IP。应用无需对公网开放 8765、5432、5173。
2. 安装 Docker Engine 和 Compose 插件。确认 `docker compose version` 可运行。
3. 创建 `/srv/storyloop-data`。只有系统盘时，该目录可暂时放在系统盘上；应定期将数据库备份复制到 ECS 以外。以后增加数据盘时，先用 `lsblk -f` 核对设备，再将数据迁移到挂载点并设置开机自动挂载；不要假定设备名。
4. 将私有剧本放在 `/srv/storyloop-private`。目录内需要 `catalog.json` 和其中引用的剧本包，例如 `winter-show/`。剧本包路径相对于 `catalog.json`，不需要复制进公开仓库。当前本地可使用 `D:\ai\romance-validation-private\catalog.json` 与同目录的 `winter-show/`；旧版 `portal-catalog.json` 含指向本机其他目录的条目，不能直接用于容器。

官方剧本仍由本地只读挂载提供。用户上传剧本写入 `/srv/storyloop-data/uploads`，作者与版本元数据写入 PostgreSQL；上传包不会写入官方目录。备份数据库时，也要备份 `/srv/storyloop-private` 和 `/srv/storyloop-data/uploads`，保持数据库记录与发布包版本一致。后期可将用户发布包迁往私有 OSS。

## 配置与启动

在 ECS 上克隆仓库，然后进入 `packages/platform/deploy/ecs`：

```sh
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

- `POSTGRES_PASSWORD` 使用 URL 安全的随机字符串，例如 `openssl rand -hex 32` 的输出。数据库首次初始化后，不能只修改此值来轮换已有数据库密码。
- `STORY_BAILIAN_API_KEY` 使用百炼**按量付费** API Key。`STORY_BAILIAN_BASE_URL` 必须与 Key 所属地域一致；当前 ECS 示例使用中国香港的 `https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1`。Token Plan 个人版 Key 不用于公开应用后端。
- 故事任务默认使用 `deepseek-v4.1-flash` 的非思考模式，并直接用工具调用生成结构化结果，避免该端点对 `response_format` 返回 400 后重试；各任务可在 `config/online.json` 的 `models.tasks` 中单独换模型。更换模型时也要核对 `models.generate_kwargs`、`models.structured_output_transport` 与 `billing.models` 费率。可选玩家画像仍独立使用 Qwen。
- `STORY_ALLOWED_HOSTS` 填玩家访问的 IP 或域名，不含协议和端口；`STORY_ALLOWED_ORIGINS` 填浏览器完整来源，例如 `https://<当前公网 IP>`。公网 IP 或域名变化时同步修改两项。
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

线上注册需要一次性邀请码。首次启动后，在 `packages/platform/deploy/ecs` 目录执行下面的命令生成邀请码，再通过安全渠道交给内测玩家。每个邀请码只能注册一个账号，默认 30 天有效；登录不需要邀请码。

```sh
docker compose exec api python -m storyloop_platform.cli.signup_invite --count 5
```

首个管理员应先注册普通站内账号，再由有服务器权限的运维人员指定该用户名执行引导命令：

```sh
docker compose exec api python -m storyloop_platform.cli.bootstrap_admin <站内用户名> --config /app/config/online.json
```

命令只为现有账号授予管理员角色，不创建默认账号或密码。管理员重新加载页面后可打开“管理工作台”，授予审核员角色、审核用户提交的固定剧本版本、调整公开版本状态，并查看操作记录。审核员的隔离试玩最多 12 回合，费用由平台承担。

内测邀请码也可在“管理工作台 → 邀请码”中生成、查看使用状态和撤销未使用的邀请码。每次可生成 1–20 枚，每枚仅供一次注册，30 天后到期。明文仅在创建响应中返回，离开或刷新页面后无法再次查看；数据库只保存哈希，管理员应在生成后立即复制并妥善传达。服务器 CLI 仍可用于运维发码，旧邀请码的使用状态不受此功能影响。公测的“完成首次游玩后发码”仅是后续资格策略，目前普通账号不能发码。

Nginx 对注册、登录和创建存档入口设置了按来源 IP 的请求速率限制。一个玩家账号的回合在单 API worker 内串行处理，避免多个存档同时通过同一笔余额检查。

网页登录使用 7 天有效的 `Secure`、`HttpOnly`、`SameSite=Lax` 会话 Cookie；后端数据库只保存令牌哈希。登录和写入请求必须来自配置的 HTTPS Origin。部署认证方式切换后，已有浏览器标签页需要重新登录一次，存档不会丢失。本地 CLI 仍支持 Bearer 令牌。

### 可选玩家画像

`STORY_PLAYER_MEMORY_ENABLED=0` 是默认值，**不提炼画像，也不为画像调用百炼**。内测需要启用时，将 `.env` 中此值改为 `1` 并重启 API。玩家仍需在“玩家画像”页面自行开启；关闭后停止采集新输入，清空按钮会删除其画像和待提炼输入。

Mem0 OSS 是开源 Python 库，**不是阿里云对象存储 OSS**。本部署将其嵌入现有 API 容器，以 `/srv/storyloop-data/memory` 中的本地 Qdrant 保存提炼结果，不增加 Mem0 服务或对象存储账单。此目录应随数据库一起备份。当前单 API worker 可使用嵌入式 Qdrant；增加多个 API 副本前，需改为共享向量服务。

开启的玩家每累计 6 条至少 12 字的非命令输入，且距上次提炼至少 12 小时，才触发一次后台提炼。Mem0 使用当前百炼香港端点上的 `qwen3.8-flash` 与 `text-embedding-v4`；调用会产生平台百炼费用，内测期间**不扣玩家积分**。提炼失败会重试，不中断游戏回合。画像仅供主控和叙述层参考，不写入 NPC 上下文或权威游戏状态。`config/online.json` 的 `player_memory` 可更换模型与向量维度；更换维度时应迁移向量集合，不要直接复用旧集合。

浏览器入口为 `https://<当前公网 IP>/`，HTTP 自动跳转 HTTPS。Nginx 使用 Let's Encrypt 的公网 IP 证书，证书约 6 天到期，必须保持自动续期。证书 lineage 固定命名为 `storyloop`；首次部署前，先使用仅含 ACME 挑战路径的 HTTP 配置签发证书，再启用 443 配置；证书目录为 `/srv/storyloop-data/letsencrypt`。公网 IP 改变时必须重新签发该 lineage，并同步修改 `.env` 的允许主机与来源。服务器安装并启用续期计时器：

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
