# 可复现验证

正式基线为 Python 3.12、Node.js 24。`uv.lock` 由 uv 0.11.25 根据 `pyproject.toml` 生成，保留 Windows/Linux 平台标记和可选依赖；前端使用 `packages/platform/web/package-lock.json`。不把本机 `pip freeze` 当作跨平台锁文件。

在仓库根目录、清除继承的 `PYTHONPATH` 后执行：

```sh
python -m pip install uv==0.11.25
uv sync --locked --all-extras
uv run --frozen --all-extras python -m pytest tests packages/harness/tests -q
cd packages/platform/web
npm ci
npm test
npm run build
# Linux CI 使用 Chromium；Windows 配置使用本机 Edge。
npx playwright install --with-deps chromium
npm run test:e2e
```

`pytest` 同时发现既有 unittest 和新增函数式故障回归；单独执行 unittest discovery 会遗漏后者。浏览器测试通过真实 React 页面操作，并模拟 API/SSE 响应，覆盖审核乱序、多版本送审、未开始回合恢复编辑、断流后沿用原请求。它们不等于真实后端联调或真实模型质量验收。

`.github/workflows/ci.yml` 配置先行的 Linux harness 作业，以及依赖它的 Windows/Linux platform 作业（Linux 同时执行前端与浏览器验证）；使用占位模型 Key，不配置生产密钥、数据库或私有内容。首次远程运行尚待推送后验证。SQLite 旧表升级由 `test_environment_profiles.py` 覆盖；PostgreSQL 并发、迁移、恢复及 Linux 实际运行仍需取得独立证据。

更新依赖时显式执行 `uv lock` 并评审差异，再运行完整验证。日常安装使用 `--locked`，避免声明与锁文件不一致时静默重新解析。部署 Dockerfile 目前仍使用 pip 范围依赖；部署消费锁文件和镜像复现属于后续发布任务。

## 独立发行包验证

CI 的 harness 作业从锁文件只导出 harness 测试依赖，构建 wheel，安装精确版本
`storyloop-harness==0.1.0`，执行包内测试（包含静态及实际导入边界），再将示例
复制到 checkout 外用 `python -I` 运行。成功后上传 wheel。

platform 作业下载该制品，从锁文件导出平台依赖时排除所有 workspace 包，
用 `--no-index --no-deps --find-links` 安装同一精确 harness 版本，独立构建并
安装平台 wheel；`pip check` 校验依赖。随后在 checkout 外执行离线 HTTP
玩家回合，执行后端全集、公开导入边界及独立安装回归，最后执行前端与浏览器测试。
运行测试使用已安装 wheel，未设置源目录 `PYTHONPATH`，也不执行 editable sync。

从仓库根目录可复现构建（需 uv 0.11.25）：

```sh
uv build --no-sources --wheel packages/harness --out-dir dist
uv build --no-sources --wheel packages/platform --out-dir dist
```

在仓库外建立并激活一个全新 Python 3.12 环境，使用上述 dist 的绝对路径：

```sh
python -m pip install --find-links /absolute/path/to/dist 'storyloop-harness==0.1.0'
# 将 packages/harness/examples 复制至当前目录，再运行：
python -I examples/offline_turn.py
python -m pip install --find-links /absolute/path/to/dist 'storyloop-platform[portal]==0.1.0'
python -I -c "import storyloop_harness, storyloop_platform; from storyloop_platform.cli import portal_api"
python -m pip check
```

`tests/test_platform_wheel.py` 自动复制两个包到 checkout 外独立构建，在新虚拟
环境安装 wheel，并检查旧命名空间消失、默认配置、离线 HTTP/SQL 回合、CLI
帮助与 Alembic 入口。它需要 `uv` 在 PATH 中以及可用的依赖索引或完整本机缓存。
`tests/test_platform_import_boundary.py` 与 harness 包内边界测试禁止反向导入
和平台依赖 harness 内部模块。测试完整运行命令见上文。

本地开发的 `uv sync` 使用 workspace 源；它不能替代上述制品验证。真实模型
效果、生产密钥、真实 PostgreSQL 并发与远程 GitHub Actions 执行结果需另行取得
证据。浏览器测试模拟 API/SSE；独立 wheel smoke 则使用真实本地 API/SQL 与
确定性离线模型，不发起外部模型请求。
