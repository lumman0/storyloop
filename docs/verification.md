# 可复现验证

正式基线为 Python 3.12、Node.js 24。`uv.lock` 由 uv 0.11.25 根据 `pyproject.toml` 生成，保留 Windows/Linux 平台标记和可选依赖；前端使用 `web/package-lock.json`。不把本机 `pip freeze` 当作跨平台锁文件。

在仓库根目录、清除继承的 `PYTHONPATH` 后执行：

```sh
python -m pip install uv==0.11.25
uv sync --locked --all-extras
uv run --frozen --all-extras python -m pytest tests -q
cd web
npm ci
npm test
npm run build
# Linux CI 使用 Chromium；Windows 配置使用本机 Edge。
npx playwright install --with-deps chromium
npm run test:e2e
```

`pytest` 同时发现既有 unittest 和新增函数式故障回归；单独执行 unittest discovery 会遗漏后者。浏览器测试通过真实 React 页面操作，并模拟 API/SSE 响应，覆盖审核乱序、多版本送审、未开始回合恢复编辑、断流后沿用原请求。它们不等于真实后端联调或真实模型质量验收。

`.github/workflows/ci.yml` 配置 Windows/Linux 后端和 Linux 浏览器验证；使用占位模型 Key，不配置生产密钥、数据库或私有内容。首次远程运行尚待推送后验证。SQLite 旧表升级由 `test_environment_profiles.py` 覆盖；PostgreSQL 并发、迁移、恢复及 Linux 实际运行仍需取得独立证据。

更新依赖时显式执行 `uv lock` 并评审差异，再运行完整验证。日常安装使用 `--locked`，避免声明与锁文件不一致时静默重新解析。部署 Dockerfile 目前仍使用 pip 范围依赖；部署消费锁文件和镜像复现属于后续发布任务。
