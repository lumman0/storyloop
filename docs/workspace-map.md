# 工作区运行基线与归并清单

核对日期：2026-10-05。正式运行与验证根目录选定为 `D:/ai/storyloop-secure-session`。下列远程差异来自缓存的 `origin/main`，本次未 fetch，不能据此断言实时远程状态。旧目录继续保留。

| 目录 | 分支 / HEAD | 与本地 origin/main 的差异 | 用途及后续处理 |
| --- | --- | --- | --- |
| `D:/ai/storyloop-secure-session` | `feature/campaign-prologue` / `2a8dd87c30fee2ac0aad5c10b0635eb97ff3ed70` | 独有 0，落后 0 | 最新功能工作树；本计划的正式代码根目录。准备式开场的既有未提交成果保留，单独评审。 |
| `D:/ai/npc-word-agent-upload` | `main` / `223e75e9693d5851360b6ec205dbd6a9923a95b0` | 独有 0，落后 38 | 同仓库旧 main；日志和部署改动逐项核对后单独归并，不能覆盖最新实现。 |
| `D:/ai/storyloop-romance-harness` | `feature/turn-stream-and-pacing` / `64cc3fe0e853e7e9ac9688932f86a930033402bc` | 独有 0，落后 46 | 较早功能工作树；核对时无未提交文件，本次不归档。 |
| `D:/ai/story-harness` | `main` / `5f39d8378b979afe11d396bc22ef9b2038d55911` | 独有 0，落后 0（独立仓库） | 早期独立原型，保留参考；其 `.venv` 曾被其他目录共用，不再作为正式运行入口。其 origin/main 与上方仓库不可直接比较。 |
| `D:/ai/romance-validation-private` | 独立内容工作区 | 本次未盘点其版本及文件 | 私有剧本、素材和验证脚本；保持独立，不复制进公开仓库。后续明确脚本的代码、内容和配置来源。 |
| `D:/ai/langfuse-local` | 第三方基础设施 | 本次未盘点其版本及文件 | 外部可观测服务；只维护集成与部署入口。 |

## 既有未提交成果

本表记录本轮开始前的改动，排除本轮正在实施的环境检查与生命周期修复；不表示已完成评审或提交。

| 来源 | 文件 | 去向 |
| --- | --- | --- |
| 旧 main 日志实现 | `src/story_harness/cli/portal_api.py`、`src/story_harness/portal/http_api.py`、`src/story_harness/portal/service.py`、新增 `src/story_harness/portal/logging_config.py` 和 `tests/test_logging.py` | 独立审查日志初始化及隐私行为，通过回归后单独提交 / 归并。 |
| 旧 main 部署实现 | `.gitignore`、`deploy/ecs/.env.example`、`deploy/ecs/README.md`、`deploy/ecs/compose.yaml`、`deploy/ecs/nginx.conf`、`docs/deployment.md` | 逐项对照最新部署配置，保留仍需要的差异，独立于功能提交。 |
| 最新工作树准备式开场 | `src/story_harness/agents/prologue_generator.py`、`src/story_harness/portal/service.py`、`src/story_harness/portal/user_scenarios.py`、`src/story_harness/world/scenario.py`、`src/story_harness/world/story_blueprint.py`、`tests/test_source_driven_story.py`、新增 `src/story_harness/world/prepared_opening.py` | 保留作者成果，按照准备式开场计划及 T08 单独评审、验证和提交。 |
| 最新工作树开场设计 | `docs/superpowers/plans/2026-10-05-prepared-story-start.md`、`docs/superpowers/specs/2026-10-05-prepared-story-start-design.md` | 作为准备式开场的设计依据保留。 |

## 独立环境与入口

后续完整回归已补齐 `.[observability,player-memory,test]`，并通过离线 `ensurepip` 安装 pip，使 README 中的 `.venv/Scripts/python.exe -m pip` 命令可直接使用。现已生成 `uv.lock`，在另外新建的锁定 Python 3.12 环境完成 314 项后端测试（另含 21 个子测试）；前端工具测试 18 项、Playwright 浏览器交互 5 项和生产构建均通过。浏览器使用实际页面与替身 API。仍有一个第三方 DashScope 弃用警告；这些结果不涵盖 PostgreSQL、Linux 实测和真实模型端到端质量。

已创建正式工作树的独立 `.venv`，基于 CPython 3.12.14，`include-system-site-packages=false`，通过 `uv pip install --python .venv/Scripts/python.exe -e ".[agents,portal]"` 安装声明依赖。首次离线安装因缓存缺少 agentscope 失败，随后联网安装成功。依赖安装没有指向旧目录的 site-packages；共享下载缓存 `D:/ai/.uv-cache` 不等于共享环境。可复现依赖现由 uv 0.11.25 生成的 `uv.lock` 管理，详见[验证说明](verification.md)；部署镜像消费锁文件仍待完成。

使用新终端，在正式代码根目录执行 README 的检查与离线示例。PowerShell 可用 `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue` 清除继承值；CMD 可用 `set PYTHONPATH=`。配置默认来自 `config/local.json`，线上需显式提供实际配置，公共示例内容来自 `examples/`，私有目录通过外部配置接入。

已在独立解释器中清除 `PYTHONPATH` 后验证：`scripts/check_environment.py --config config/local.json` 成功，导入路径指向本工作树；`python -m unittest discover -s tests -p test_check_environment.py -v` 的 4 项测试通过；离线 `interaction_demo examples/freeform` 完成四轮并退出 0。离线示例在 Windows 沙箱内等待 asyncio 初始化，改用允许的沙箱外离线进程后完成；未访问真实模型。这里只验证 T01 入口，不代表全套回归或线上部署通过。

本次只读核对发现 `D:/ai/langfuse-local/play-storyloop.cmd` 仍设置 `PYTHONPATH=D:/ai/npc-word-agent-upload/src`，并调用 `D:/ai/story-harness/.venv/Scripts/python.exe`。该入口尚未迁移，不能作为正式基线的验证入口；其 `--check` 只检查观测凭据是否加载。本次未改动外部启动脚本或私有验证脚本。

**T01 仍为部分完成：** 运行基线、独立环境与安全检查已建立；旧 main 日志 / 部署改动和准备式开场改动尚未逐项评审、分别提交，外部启动及私有验证入口尚未迁移。没有删除、归档旧目录，也没有迁移生产数据。
