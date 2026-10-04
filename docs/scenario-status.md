# 剧本状态字段

剧本通过 `manifest.json` 的 `initial_state` 定义存档里的初始值，通过可选的 `status_fields` 指定哪些值进入玩家界面。Day 与时段由剧本时间单位和已提交的游戏时钟计算，不需要模型生成文本数值。没有 `status_fields` 的旧剧本仍可直接运行。

```json
{
  "time_unit": "slot",
  "ticks_per_day": 4,
  "initial_state": {
    "actors": {"player": {"location": "villa"}},
    "player_stats": {"mood": 80},
    "relationships": {"zhang": {"met": false, "affinity": 0}}
  },
  "status_fields": [
    {
      "id": "mood",
      "label": "心情值",
      "path": ["player_stats", "mood"],
      "description": "玩家当前心情；普通寒暄不应改变",
      "bounds": {"min": 0, "max": 100, "max_delta": 3}
    },
    {
      "id": "zhang_affinity",
      "label": "与章的好感度",
      "path": ["relationships", "zhang", "affinity"],
      "when": {"path": ["relationships", "zhang", "met"], "equals": true},
      "bounds": {"min": 0, "max": 100, "max_delta": 2}
    },
    {
      "id": "location",
      "label": "当前位置",
      "path": ["actors", "player", "location"]
    }
  ]
}
```

- `path` 必须指向 `initial_state` 中已经存在的字符串、整数或布尔值；字段 `id` 和路径不能重复。
- 省略 `bounds` 时只读取存档状态。剧情事件、特殊行动或其他已提交事件仍可修改该路径；展示层不会自造值。现有恋综 `campaign.affinity` 可以先用这种方式展示，避免重复结算。
- 整数项设置 `bounds` 后，默认单次生成模式会在生成故事回应时一并提议增减。`max_delta` 限制单回合变幅，运行时校验路径和数值范围，再把变化作为 `status_review` 事件写入存档。没有足够证据时返回空变化。旧的 `multi_agent_beta` 模式使用独立轻量模型评估。
- `visible: false` 会让字段只留在存档，不进入玩家 API。`when` 可以让字段在剧本状态满足条件后才出现，例如认识角色后显示关系值。
- 默认单次生成模式的状态提议不会额外增加模型调用；它的 Token 仍进入现有回合计费与 Langfuse 链路。

状态值属于存档的权威快照，NPC 的上下文仍由单独投递给该角色的观察和对话构造。一个关系数值被更新，不等于该 NPC 已经获知玩家的其他经历。
