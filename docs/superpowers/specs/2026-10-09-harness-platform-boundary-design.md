# StoryLoop harness 与 platform 包边界

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

日期：2026-10-09

## 目标与范围

StoryLoop 最终由 GitHub organization 下的两个公开仓库组成：`storyloop-harness` 是供其他互动叙事项目安装的 Python 运行时库，`storyloop-platform` 是使用该库的玩家与创作者平台。先在当前仓库内完成两个包的边界、安装和集成验证，再拆分 Git 仓库。本设计约束这两个阶段的职责与验收条件；不在本阶段创建 GitHub organization、迁移远程仓库或发布软件包。

`storyloop-harness` 聚焦互动叙事，不设计成通用 Agent 框架。当前默认的 `single_call` 必须是它的首个正式引擎。AgentScope 是模型与 Agent 能力的实现依赖，不能用“是否采用 ReAct”决定业务边界。

多 Agent beta 停止新增功能。当前实现与测试先以 Git 标签和归档分支保存；不再允许新配置选择 `multi_agent_beta`。删除活动代码前，要识别并处理旧存档中尚未完成的 `npc_reply` 工作，不能让旧存档被静默跳过。归档分支不属于日常发布与回归范围。

## 方案取舍

| 方案 | 取舍 |
| --- | --- |
| 立即按目录复制到两个仓库 | 能快速展示两个仓库，但当前平台装配、默认引擎和多 Agent 类型交叉引用，复制后难以定义唯一的契约与版本来源。 |
| **先形成两个可安装包，再拆仓库** | **采用。** 单仓内先验证导入方向、安装、回合行为和平台集成；拆仓时主要改变代码托管与版本获取方式。 |
| 永久保留单仓双包 | 开发协调成本低，但无法完成用户希望的独立开源库与独立仓库。 |

## 包职责

| `storyloop-harness` | `storyloop-platform` |
| --- | --- |
| 剧本包格式、世界书、角色及玩家可见信息投影。 | React 前端、FastAPI、HTTP/SSE、Cookie 与鉴权。 |
| 事件、观察、快照、状态提议校验、故事时间与回合执行契约。 | 账号、剧本目录、上传与审核、存档所有权、邀请码。 |
| 默认 `single_call` 场景生成与确定性的事件提交；受限的任务处理。 | 积分钱包、定价与结算快照、请求幂等回执、额度策略。 |
| 模型端口与 AgentScope 适配、`GameStore` 存储协议、用量数据契约、可复用的运行时遥测端口。 | SQLAlchemy 仓储与迁移、平台数据库事务、Mem0 玩家画像、部署与运维配置。 |
| 最小内存存储适配与公开示例，使独立安装后能运行一段示例回合。 | 面向具体产品的呈现、运营规则与对外 API 契约。 |

公共 Python 发行包和导入名分别是 `storyloop-harness` / `storyloop_harness` 与 `storyloop-platform` / `storyloop_platform`。过渡期保持一个 Git 仓库，两个包各有自己的 `pyproject.toml`、测试入口和依赖声明；`platform` 通过版本化依赖使用 `harness`。本地开发可使用 workspace/path 依赖，发布后使用固定的兼容版本范围。`harness` 不得导入 `platform`，`platform` 只从 `harness` 的公开 API 导入，不能依赖其内部模块路径。

`harness` 中的存储接口只描述回合所需操作；SQL 实现由 `platform` 提供。库的最小内存实现用于示例和契约测试，不承诺持久化。计费用量由运行时返回或通过明确的用量端口收集；定价、扣费和玩家余额只在平台。剧本包的解析与运行校验属于库；上传、版本发布、审核和文件生命周期属于平台。

## 公共执行契约与数据流

公开入口以 `TurnEngine`、`TurnInput`、`TurnOutcome`、`ScenarioPackage`、`GameStore` 和 `ModelPort` 为核心。`TurnInput` 包含存档标识、玩家行动和已选择的剧本版本；`TurnOutcome` 包含可呈现文本、已提交的事件与观察、最终快照及模型用量。具体字段由现有 `SingleCallGameSession` 与 `TurnOutcome` 归并，避免同时维护两套相似结果类型。运行时只接收已经通过平台授权的存档与剧本，不接触账号、Cookie 或积分余额。

普通回合的调用顺序固定为：平台验证身份与存档所有权 → 平台检查请求幂等回执及额度 → harness 通过 `GameStore` 读取权威世界状态并投影上下文 → `single_call` 生成提议 → harness 校验并提交事件、观察和快照 → 平台保存结算快照、处理积分和回执 → 平台经 HTTP/SSE 返回结果。`GameStore.commit` 继续以预期版本保护并发写入。模型生成失败时不提交世界状态；提交成功但响应丢失时，平台依据既有结算与回执恢复。跨库拆分不得改变这些失败语义。

平台中的 Mem0 玩家偏好和 Langfuse 服务配置保留在平台；harness 只接受可选、无平台身份信息的模型和遥测端口。玩家偏好、角色观察与 SQL 权威事实继续分离。

## 现有代码的迁移边界

1. 将 `core/` 的故事事件与状态契约、`world/` 的剧本解析与运行校验、`runtime/single_call.py`、场景上下文投影及其必要的生成模型移入 harness。把 `GameStore` 协议从当前同时包含 `SQLiteGameStore` 的模块中分离。
2. 将 `portal/`、`web/`、账号与钱包 SQL 仓储、审核和内容生命周期、部署配置移入或保留在 platform。平台负责组装 `TurnEngine`，不负责生成内部剧情事件。
3. 把 `single_call.py` 对 `agents/main_agent.py` 中 `MainDecision` 的依赖改成 harness 自己的共享契约。清除 `service.py` 对 beta 具体类的直接装配；旧 `npc_reply` 兼容处理留在平台的迁移适配层，直到旧数据处理完毕。
4. 先做导入与安装边界，再做目录搬迁；每一批移动后保持现有可玩路径和测试可运行。两个包都能在单仓内独立构建，平台安装不依赖仓库根目录的 `PYTHONPATH`。

## 封存多 Agent 路线

在现有 AgentScope 2.0.9 升级改动形成独立提交且回归通过后，为最后可运行的 beta 打标签并建立归档分支。平台配置只接受正式的 `single_call`；旧配置明确报错并提示修改，不自动切换引擎。执行一次旧待办数据盘点；存在未完成 `npc_reply` 时，保留可调用的兼容适配并通过恢复测试，或完成显式迁移后再删除。README、架构图和配置示例不再把 beta 描述为当前可选产品能力。恢复 beta 时应另立设计与回归计划。

## 分仓条件与迁移

包边界完成后，才建立 StoryLoop organization 并处理仓库迁移。现有远程仓库作为 `storyloop-platform` 延续历史、Issue 和 PR；`storyloop-harness` 从已验证的包目录提取，并保留可追溯提交历史。平台在 CI 中安装 harness 的明确版本，不能依赖相邻工作目录。拆仓后分别拥有发行说明、贡献指南、测试和版本；跨仓改动先发布 harness，再更新 platform 依赖。更新本地 remote、CI、部署、文档和徽章中的旧仓库地址，并检查 GitHub 转移后的重定向。

## 验收

- `storyloop-harness` 可单独构建、安装并运行公开示例；不安装 FastAPI、React、账号或钱包组件也能完成一次离线故事回合。
- 静态导入检查确保 harness 不引用 platform，platform 不引用 harness 内部模块；仓库根目录以外安装时两个包均可导入。
- 默认单次调用回合、角色信息隔离、状态校验、事件提交、取消/失败及结算恢复的现有回归继续通过；平台的前端与 API 冒烟验证继续通过。
- 新配置无法选择 `multi_agent_beta`；旧待办有明确的恢复或迁移行为，相关测试覆盖。
- 分仓后平台 CI 仅依赖已发布或固定 Git 版本的 harness，两个仓库的测试分别通过。真实模型质量与性能改进不作为本次结构调整的验收门槛。

## 不在本次范围

不新增多 Agent 功能、消息队列、微服务、通用 Agent 插件系统或新的生产数据迁移策略。不改变已发布剧本包及存档的业务含义。GitHub organization 名称可用性、账号权限及远程迁移在包边界通过后核实。
