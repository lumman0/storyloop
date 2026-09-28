# NPC World Agent Harness

一个纯命令行的互动叙事 harness。世界事实由事件和状态快照管理；观察按接收者投递；主控和每个 NPC 分别运行 AgentScope ReAct，上下文互相隔离。回合调度器按预算处理 NPC 回复和背景事件，支持在玩家聊天时继续推进游戏时间。

此仓库只包含框架代码、测试以及原创的合成验证剧本。`examples/freeform` 展示背景资料型世界书，`examples/scheduled` 展示规则和日程型世界书。它们不依赖任何私人剧本原件。

## 安装

需要 Python 3.12 或更新版本。在 PowerShell 中进入仓库目录：

```powershell
py -3.12 -m venv .venv
& '.venv\Scripts\python.exe' -m pip install -e '.[agents]'
```

## 离线验证

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.venv\Scripts\python.exe' -m story_harness.cli.demo_check
```

离线演示使用确定性的模型替身，不发起 API 请求。两个合成剧本也可以分别运行：

```powershell
& '.venv\Scripts\python.exe' -m story_harness.cli.interaction_demo examples\freeform
& '.venv\Scripts\python.exe' -m story_harness.cli.interaction_demo examples\scheduled
```

## 接入模型

[`config/bailian-token-plan.json`](config/bailian-token-plan.json) 将主控、NPC 回复、待办选择和叙述映射到可配置的模型 ID，同时配置接口地址、步数预算和 SQLite 路径。百炼示例将 `tool_choice_policy` 设为 `auto_only`，以兼容 Qwen 不支持强制工具调用的接口；换用支持强制工具调用的模型可设为 `native`。密钥通过配置的 `api_key_env` 指向环境变量，不能写进配置文件或存档。

```powershell
& '.venv\Scripts\python.exe' -m story_harness.cli.react_play examples\freeform --config config\bailian-token-plan.json --db game.sqlite3 --game-id demo
```

缺少环境变量时，终端会隐藏读取 API Key。当前提供 SQLite 存储和进程内 AgentScope memory；PostgreSQL、Redis、轻量模型 NPC 预筛选、通用自由动作裁定及语义 RAG 仍是扩展点。

## 源码分区

| 目录 | 职责 |
| --- | --- |
| `core/` | 事件、状态归约、动作规则和物理观察 |
| `world/` | 剧本包加载与世界书权限查询 |
| `runtime/` | 玩家输入、动态待办、日程和完整回合 |
| `agents/` | 主控、NPC、待办选择的 AgentScope ReAct 实现 |
| `adapters/` | SQLite、模型配置及可选 Langfuse 观测 |
| `cli/` | 终端入口与离线演示 |

世界状态以事件提交为准。NPC 的 memory 只保存其独立对话上下文，不能直接改写权威状态。示例动作必须在剧本包中声明，模型只能选择动作 ID，状态效果由规则校验后生成。
