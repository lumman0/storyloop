# 长存档读取性能基线

2026-10-05 的 T10 性能切片建立离线基线、索引对照及当前代码复测。它不验证模型耗时、并发请求、PostgreSQL、分页、客户端关闭或优雅停机。

## 运行方法

在安装已有 `agents` 依赖的独立环境中，从仓库根目录运行：

```powershell
.venv\Scripts\python.exe scripts/benchmark_long_save.py > baseline.json
.venv\Scripts\python.exe scripts/benchmark_long_save.py --turns 100 --repeats 1
.venv\Scripts\python.exe scripts/benchmark_long_save.py --experimental-observation-index > index-comparison.json
```

脚本强制导入本 checkout 的 `src`，不读取配置、真实存档或 `DATABASE_URL`，不创建模型或服务客户端。每个规模单独创建、迁移并关闭临时 SQLite 数据库；正常退出时删除它。Windows 受限沙箱中，应先将 `TEMP`、`TMP` 指向可写临时目录。

规模仅允许 100、1,000、10,000，重复次数为 1–5，默认三次。每项默认有 10 秒 SQLite 执行预算，可用 `--sql-timeout-seconds 1..30` 调整。SQLite progress handler 中断超时 SQL，报告 `sql_timeout` 并停止重复该项；这不是完整结果。预算不强制抢占 SQL 返回之后的 Python 计算。退出码 0 表示报告生成成功，不能当作性能验收通过。

实验开关仅在临时数据库缺少 `(game_id,event_id,recipient_id)` 索引时添加它，已有迁移提供该索引时不重复创建。报告记录每点的实际观察表索引及 actor-history 查询计划。默认路径完全采用当前生产迁移，因此优化后运行得到的是新结果，不能覆盖旧基线。

## 数据及测量口径

- 从公开 `examples/freeform` 创建合成港口场景，固定三名 NPC；没有私有素材。
- 每回合一个玩家输入、三个 NPC 回答，共四个事件；玩家场景观察、三个 NPC 听见输入、三个玩家听见回答，共七个观察。
- 10,000 回合对应 40,000 事件、70,000 观察；玩家可见历史 40,000 条、输入历史 10,000 条、玩家 agent 历史 50,000 条。未模拟 NPC 间旁听、后台工作、钱包或持久化模型计划的大型 JSON。
- 直接批量写入符合读取接口的合成事件与观察；准备数据不测运行时提交吞吐。没有压缩 checkpoint，模拟尚未压缩的长历史。
- 实际调用 `SceneContextProjector.project`、`observations_for`、`player_inputs_for`、`agent_context_entries`。快照加载、导入、迁移、写入、结果摘要和 EXPLAIN 不计入读操作耗时及 SQL 次数。
- 耗时为开启 `tracemalloc` 时的三次中位数；峰值是该操作新增 Python 分配的最大值，**不包含进程 RSS、SQLite 原生内存、解释器及预加载依赖**。它不是整机内存。
- SQL 次数按 SQLAlchemy `before_cursor_execute` 统计执行语句，不代表扫描行数或内部 VM 工作量。没有刷新 OS 文件缓存；按固定顺序测量，无额外预热，先前操作会影响后续缓存。

## 优化前基线

环境：Windows 11 build 26200；CPU 报告 `Intel64 Family 6 Model 183 Stepping 1`；独立环境 Python 3.12.14、SQLite 3.53.1、SQLAlchemy 2.1.3、AgentScope 1.0.21。Git HEAD 为 `2a8dd87c30fee2ac0aad5c10b0635eb97ff3ed70`，工作区有未提交改动。这次测量在近期读取限量及迁移 0014 之前完成。

| 回合 | 操作 | 中位耗时 ms | Python 峰值 MiB | SQL 次数 |
| ---: | --- | ---: | ---: | ---: |
| 100 | 上下文组装 | 71.728 | 0.590 | 15 |
| 100 | 玩家可见历史 | 6.902 | 0.287 | 1 |
| 100 | 玩家输入历史 | 2.483 | 0.116 | 1 |
| 100 | 玩家 agent 历史 | 23.632 | 0.480 | 2 |
| 1,000 | 上下文组装 | ≥10,000，SQL 中断 | 4.887，部分执行 | 10，部分执行 |
| 1,000 | 玩家可见历史 | 55.010 | 2.872 | 1 |
| 1,000 | 玩家输入历史 | 14.176 | 1.115 | 1 |
| 1,000 | 玩家 agent 历史 | 5,038.516 | 4.796 | 2 |
| 10,000 | 上下文组装 | ≥10,000，SQL 中断 | 11.198，部分执行 | 4，部分执行 |
| 10,000 | 玩家可见历史 | 599.010 | 28.984 | 1 |
| 10,000 | 玩家输入历史 | 138.626 | 11.191 | 1 |
| 10,000 | 玩家 agent 历史 | ≥10,000，SQL 中断 | 6.830，部分执行 | 2，部分执行 |

100 回合最终上下文仅保留玩家 14 条和每名 NPC 11 条，UTF-8 请求为 13,363 字节。但裁剪发生在全历史读取之后，输出有界没有使读取有界。超时行的耗时只给出已达到的下界，峰值和查询次数不能冒充完成测量。

无新索引的 actor-history EXPLAIN：

```text
SEARCH e USING INDEX events_game_version (game_id=? AND state_version>?)
SEARCH o USING INDEX observations_game_recipient (game_id=? AND recipient_id=?)
USE TEMP B-TREE FOR LAST 2 TERMS OF ORDER BY
```

事件表驱动关联，但观察查找没有事件 ID。结合规模增长和下述同代码索引对照，结果支持“重复扫描同一角色观察造成额外开销”的判断；SQL 语句数本身看不出这一问题。

## 仅索引对照

对照冻结原 `SQLGameStore` 与 `SceneContextProjector`，保持三次重复、相同数据及计时方式，避免并行开发中的读取限量混入结果。原模块 SHA-256：

```text
sql_store.py  e94c760db8f17719086f3d4fdc7b2497d327cfa03f5c3ae71cede930d9762fec
scene_turn.py d3a846be638006be42adab5cffb5e161e3fc247c8df878ca8184e6ee37a4113b
```

每个规模的实际索引清单相同：`observations_game_recipient(game_id,recipient_id)` 和迁移 0014 的 `observations_game_event_recipient(game_id,event_id,recipient_id)`，均未额外创建实验索引。查询计划仍由 `events_game_version` 驱动，但观察查找变为 `game_id=? AND event_id=? AND recipient_id=?`。

| 回合 | 上下文中位 ms | 上下文峰值 MiB | SQL 次数 | 玩家 agent 历史中位 ms | 该历史峰值 MiB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 43.309 | 0.590 | 15 | 7.250 | 0.480 |
| 1,000 | 329.741 | 4.887 | 15 | 66.120 | 4.796 |
| 10,000 | 3,725.314 | 49.341 | 15 | 752.736 | 49.312 |

索引对照不会证明全历史读取已解决。即使索引消除重复扫描，返回所有行的 Python 列表、JSON 解析和历史排序仍随存档增长。

## 当前生产代码复测

随后采用相同脚本、数据、三次重复及 10 秒预算，运行包含迁移 0014、近期输入/观察 SQL 限量及输入读取去重的当前代码。没有开启实验索引，实际仍是上述两个观察表索引。读模块 SHA-256：

```text
sql_store.py  f8ad8ca542a36c78e95356bb22b8a48751c500fbdfee56b9f4012884e004c336
scene_turn.py 0aefdfc2ae43127fade269b7cc2aaf1accfc5e6bda54b9851b1620570d51922c
```

下表历史栏为“中位 ms / Python 峰值 MiB”。三项独立历史读取仍调用默认完整读取接口，用于与原基线保持可比；并非限量接口的耗时。

| 回合 | 上下文中位 ms | 上下文峰值 MiB | 上下文 SQL | 玩家可见历史 | 玩家输入历史 | 玩家 agent 历史 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 34.626 | 0.518 | 14 | 7.052 / 0.294 | 2.369 / 0.123 | 8.013 / 0.480 |
| 1,000 | 248.561 | 4.829 | 14 | 59.740 / 2.871 | 15.290 / 1.120 | 67.695 / 4.796 |
| 10,000 | 2,782.995 | 49.344 | 14 | 647.913 / 28.984 | 145.054 / 11.197 | 761.554 / 49.312 |

近期读取减少了上下文 SQL 次数和耗时，但 **10,000 回合内存没有改善**：仅索引 49.341 MiB，当前 49.344 MiB，近乎相同。未限量的 player/NPC agent 历史仍决定峰值。最终上下文仍为玩家 14 条和每 NPC 11 条。该结果尚未满足“常规上下文避免完整历史常驻内存”的 T10 验收要求。

这些运行没有隔离整机上的其他开发、测试负载，也未刷新缓存；小幅耗时差异不应当作性能回退结论。每次 JSON 报告保留逐样本耗时、峰值、SQL 次数、实际索引、模块哈希和环境，便于后续同机器比较。

## 全历史读取位置及后续工作

优化前 `SceneContextProjector.project` 两次调用 `player_inputs_for(...)[-4:]`，并在 `observations_for(...)[-6:]` 返回完整列表后切片。每名 focus actor 及玩家的 `agent_context_entries` 也在 SQL 返回完整 checkpoint 后历史，再由 `_history` 排序筛选较早相关条目与近期条目。

`SQLGameStore.observations_for`、`player_inputs_for` 默认完整返回；`agent_context_entries` 只有版本下界，没有行数上界。`SingleCallGameSession.run_turn_bounded` 在回合前后读取全部玩家观察；`proposed_options` 读取全部输入再取近期。`PlayerPortal` 的历史投影、近期输入提示和恢复路径也有全列表读取；`AgentContextProjector.prepare` 读取全部 checkpoint 后条目才判断压缩预算。

本报告保留优化前证据和同机复测。后续需分别处理 agent 相关记忆检索预算、历史稳定游标分页和回合前后观察增量读取。模型客户端和画像线程的完整关闭责任仍属于未完成的 T10 范围；本轮回合停机切片另见部署文档与 test_shutdown.py。

三份原始 JSON 分别为 `D:/ai/tmp/storyloop-performance-baseline-20261005.json`、`D:/ai/tmp/storyloop-performance-index-comparison-20261005.json`、`D:/ai/tmp/storyloop-performance-after-20261005.json`，同时保存在本轮第二检查点中。
