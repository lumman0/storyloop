# 积分计费

玩家账户注册时获得 500 积分。当前换算基准是 50 积分对应 ¥1；这是站内计价规则，暂不提供充值、退款或提现接口。已有账户第一次使用积分功能时也会获得一次初始积分。

每次游戏回合使用独立的 Token 用量收集器，记录本轮所有模型调用的输入、输出与缓存命中 Token。当前唯一回合引擎 `single_call` 在普通回合只调用一次场景模型；历史归档的 `multi_agent_beta` 曾分别调用主控、NPC、选择器和叙述器，当前配置不能选择该引擎。模型适配器只上报用量，不决定价格。回合成功后，计费策略按模型名称查询费率与倍率，汇总后向上取整到千分之一积分。失败的回合不扣费；同一 `request_id` 重试读取原回执，不重复扣费。

余额、流水和玩家回合回执存于同一 SQLite 或 PostgreSQL 数据库。结算时在单个事务内写入回执、扣减余额和新增流水。最后一个回合若超出剩余积分，实扣以余额为上限，流水仍保留完整的模型用量和应计积分，余额不会变成负数。

`config/local.json`、`config/online.json` 与 `config/bailian-token-plan.json` 的 `billing` 段定义：

- `welcome_points`：注册赠送积分。
- `points_per_rmb`：人民币参考价格到积分的换算率。
- `pricing_version`：本次费率版本，随每条流水保存。
- `models.<模型名>`：每百万输入、输出、缓存输入 Token 的人民币参考单价和 `multiplier`。更换 GLM、OpenAI 等模型时，先在模型任务路由配置中改模型，再为新模型配置费率；缺失费率时启动失败，避免漏计费。

本地与线上默认将故事任务路由到 `deepseek-v4.1-flash`，并在 `models.generate_kwargs` 中关闭思考模式。积分示例使用[百炼公开的该模型忙时价格](https://help.aliyun.com/zh/model-studio/deepseek-v4-1-flash)：每百万输入 Token ¥2、输出 Token ¥8、缓存命中输入 Token ¥0.2；这是一套可调整的站内参考费率，并非对香港账单价格的保证。原有 Qwen 费率保留，方便切换模型。专用的 `bailian-token-plan.json` 仍使用其支持清单中的 Qwen 模型。促销、地域和实际账单可能不同；调整费率时更新 `pricing_version`，历史流水不重新计价。

接口：`GET /v1/billing/wallet` 查询余额，`GET /v1/billing/ledger` 查询最近流水；两者均需要玩家登录。前端在导航栏和回合回应中显示余额与本轮扣费，在积分页展示流水和模型用量。
