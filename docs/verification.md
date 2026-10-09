# 平台验证

根 pyproject 与 uv.lock 固定公开 harness 提交 `fadbd74584852fec3ad097bb7ec8421935eaacfc`（0.2.0 候选版本）。两仓采用 MIT。升级 harness 时显式更新完整 rev，用 uv 0.11.25 执行 `uv lock` 并评审差异，然后运行以下全部检查。

构建目录 `dist/harness` 应为空。安装时显式传入该目录内的精确 wheel 路径，不能仅用 `--find-links` 搭配范围依赖，因为包索引仍可能提供其他兼容版本。

CI、Docker 和 `test_platform_wheel.py` 使用同一个 `scripts/build_harness.py` 从元数据的固定 Git 提交构建 harness wheel。缺少固定提交时该脚本报错，不使用相邻源码或浮动分支。

```sh
python scripts/build_harness.py --out-dir dist/harness
uv build --no-sources --wheel . --out-dir dist/platform
uv sync --locked --all-extras
# The shared Git wheel builder invokes pip; uv environments do not seed it.
uv pip install pip
uv run --locked --all-extras python -m pytest tests -q
cd web
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

独立安装回归会把根项目复制到 checkout 外构建平台 wheel，在新 Python 3.12 环境中安装两个 wheel，运行真实本地 HTTP/SQL 离线玩家回合、默认配置、CLI 帮助及 Alembic。测试移除继承的 PYTHONPATH，不需要生产密钥或外部模型。边界测试要求扫描到非空平台源码；harness 的反向依赖检查由独立 harness CI 负责。

发布前本地检查允许显式设置 `STORYLOOP_TEST_HARNESS_WHEEL` 为已验证 harness wheel 的绝对路径。这只证明本地制品兼容，不证明 Git 固定版本安装。CI 不设置此变量，正式验收必须移除它。

CI 安装锁定的第三方依赖以及固定 Git 构建的 harness wheel，再安装平台 wheel，运行 pip check、checkout 外 smoke、Windows/Linux 后端测试，以及 Linux 前端和浏览器检查。浏览器测试模拟 API/SSE；不能代替真实后端联调、PostgreSQL 并发或真实模型质量验收。先前 main 的远程 Actions 已通过；本次清理变更仍须取得对应提交的远程 CI 结果，Docker 运行验证尚未完成。

## 上下文投影清理回归

`tests/test_context_projection_cleanup.py` 验证仅当前路由配置以及 HTTP/SSE 对当前或未来 `npc_reply` 的拒绝，断言模型、世界、队列和账务均无副作用。`test_agent_context_window.py`、`test_scene_responder_context.py` 验证 SQL 重启后的角色历史、可见范围和输入预算；`test_single_call.py` 保留普通回合、确定性交付、取消与重试；`test_campaign.py` 保留批量留言、时钟、门槛与恢复；`test_turn_settlement_recovery.py` 验证计量快照及幂等结算。

已移除的每 NPC ReAct 工具循环、代理缓存和模型压缩器不再属于活动测试面。角色视角投影不表示共享模型内的硬隔离。测试均使用离线模型替身，不产生供应商模型费用。
