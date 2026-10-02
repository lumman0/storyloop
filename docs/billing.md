# 积分计费

玩家账户注册时获得 500 积分。当前换算基准是 50 积分对应 ¥1；这是站内计价规则，暂不提供充值、退款或提现接口。已有账户第一次使用积分功能时也会获得一次初始积分。

每次游戏回合使用独立的 Token 用量收集器，记录主控、NPC、选择器和叙述器等所有模型调用的输入、输出与缓存命中 Token。模型适配器只上报用量，不决定价格。回合成功后，计费策略按模型名称查询费率与倍率，汇总后向上取整到千分之一积分。失败的回合不扣费；同一 `request_id` 重试读取原回执，不重复扣费。

余额、流水和玩家回合回执存于同一 SQLite 或 PostgreSQL 数据库。结算时在单个事务内写入回执、扣减余额和新增流水。最后一个回合若超出剩余积分，实扣以余额为上限，流水仍保留完整的模型用量和应计积分，余额不会变成负数。

`config/local.json`、`config/online.json` 与 `config/bailian-token-plan.json` 的 `billing` 段定义：

- `welcome_points`：注册赠送积分。
- `points_per_rmb`：人民币参考价格到积分的换算率。
- `pricing_version`：本次费率版本，随每条流水保存。
- `models.<模型名>`：每百万输入、输出、缓存输入 Token 的人民币参考单价和 `multiplier`。更换 GLM、OpenAI 等模型时，先在模型任务路由配置中改模型，再为新模型配置费率；缺失费率时启动失败，避免漏计费。

当前示例费率取自阿里云百炼华北 2（北京）的公开原价：[Qwen3.8-Flash](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[Qwen3.8-Max](https://help.aliyun.com/zh/model-studio/qwen3-8-max)。促销、Token Plan 套餐和实际账单可能不同，站内费率应由运营自行调整。费率调整时更新 `pricing_version`；历史流水使用结算时记录的版本与 Token 用量，不随新配置重算。

接口：`GET /v1/billing/wallet` 查询余额，`GET /v1/billing/ledger` 查询最近流水；两者均需要玩家登录。前端在导航栏和回合回应中显示余额与本轮扣费，在积分页展示流水和模型用量。
