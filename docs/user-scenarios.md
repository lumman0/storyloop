# 用户剧本与公开审核

官方剧本由部署者维护的 `catalog.json` 加载。登录用户可以在“我的剧本”上传 ZIP 剧本包。上传后是私有草稿；开启私有试玩后，仅作者账号可以在目录中看到。作者也可以把一个固定版本提交审核，通过后进入公共目录。其他玩家不能读取未送审的草稿或创建其存档。

## 上传格式与限制

ZIP 根目录需直接包含 `manifest.json` 和其中引用的世界书 JSON；章节剧本还需 `campaign.json`。文件名仅接受英文字母、数字、下划线和短横线，以 `.json` 结尾；不接受外层文件夹、非 JSON 文件、符号链接、重复文件名或不安全路径。压缩包最大 4 MiB，最多 16 个文件，单文件解压后最大 2 MiB，全部解压后最大 8 MiB。服务端使用 `ScenarioPackage` 和 `CampaignProgram` 校验，失败时不创建草稿。

章节步骤可设置可选的 `at_subtick`，把晚餐、夜间留言等事件安排在一个剧情刻度内更晚的时点；它必须小于目录配置的 `turns_per_story_tick`。普通行动在当晚不会自动跳到次日，休息会先触发当晚尚未发生的必经事件。`message` 步骤的 `incoming` 文案是兜底；默认单次生成模式在同一次调用中生成符合条件的 NPC 私信，各角色仍使用各自的经历上下文，玩家发出的原文只交给收件人。

章节剧本可在两个 `scene` 之间插入 `{ "id": "enter", "at": 0, "kind": "continue", "prompt": "门内传来谈话声。", "label": "走进去" }`。前端将它显示为继续阅读按钮；玩家点击后才呈现后续场景或选项，故事时间不前进。作者可用多个这样的节点组织开场，角色介绍与首次选择的顺序由剧本决定。CLI 对应 `/continue` 命令。

平台建档时可选小说模式（`campaign`，主控将 NPC 结果整合为玩家第二人称正文）或剧本模式（`freeform`，玩家直接与 NPC 互动）。CLI 仍可在 `manifest.json` 使用 `"presentation_mode": "interactive"` 或 `"novel"` 指定呈现方式。当前唯一回合引擎 `runtime.turn_engine=single_call` 在普通回合只调用一次模型，以故事正文为主；玩家已知经历、相关 NPC 各自的上下文和公开剧本资料仅作为补充。模型可以附带后续行动和值得保留的角色记忆，但普通活动不需要填写行动阶段或状态增量。玩家始终可以自行输入。剧情必选节点使用剧本定义的合法选项。旧的多 Agent 引擎 `multi_agent_beta` 已归档为历史参考；当前配置仅接受 `single_call`，其他引擎值会被拒绝。

可在 `manifest.json` 写入 `"authored_prologue"`，预写完整序章。它应覆盖开局已触发的场景、公开背景、已确定的主角身份和眼前可行动的情境。若省略，平台在上传或上传新版本时调用一次 `prologue` 模型，生成结果写回不可变剧本包，再计算版本指纹；玩家建档与重开页面只读取已保存的序章，不生成也不扣玩家积分。生成仅使用开场、公开世界书和开局玩家可见场景，不读取秘密。官方剧本应预先提供该字段。`opening` 保留为互动模式的回退开场。请在 JSON 字符串中使用正常的 `\n` 换行转义，不要让正文出现字面 `\\n`。

维护官方剧本时，若包里尚无序章，可在加入目录前运行 `python -m storyloop_platform.cli.prepare_prologue 剧本目录 --config 配置文件 --title 剧本名`。该命令把生成结果写入 `manifest.json`；再次执行会直接跳过模型调用。作者上传接口在生成失败时不发布版本，保留原 ZIP 可重试。`models.tasks.prologue` 可以单独选择模型，未配置时沿用 `narration`。

## 准备式开场与身份模板

源驱动剧本在 `manifest.json` 声明 `story_blueprint` JSON 文件，并在 `authored_prologue` 中保留 `{{player_intro}}`；可另用 `{{player_name}}`。开场正文、三条 `opening_options`、完整的 NPC 角色卡和公开人物介绍在上传阶段校验。建档时只做本地身份选择与文本替换，不调用开场模型；已经保存的序章与旧存档不会因新增模板字段而重写。

玩家身份的题材由 `story_blueprint.json` 内的 `player_intro_template` 决定，`player_intro_variables` 是作者明确允许使用的变量名单。以下是科幻剧本中的相关字段，其他既有蓝本字段仍需填写：

```json
{
  "player_intro_template": "你是{{name}}，作为{{role}}登上{{ship}}。",
  "player_intro_variables": ["name", "role", "ship"],
  "player_profile_pools": {
    "engineer": [{"name": "艾然", "role": "工程师", "ship": "曙光号"}]
  },
  "setup": {
    "player_options": [
      {"id": "engineer", "label": "随机工程师", "guidance": "选择准备好的工程师身份", "source_ref": "开场设定"},
      {"id": "custom", "label": "自定身份", "guidance": "采用玩家填写的身份", "source_ref": "开场设定"}
    ],
    "tone_options": [{"id": "slow", "label": "缓慢探索", "guidance": "以观察和交流推进", "source_ref": "叙事基调"}],
    "custom_fields": [
      {"id": "name", "label": "姓名", "required": true, "max_length": 30},
      {"id": "role", "label": "职务", "required": true, "max_length": 80},
      {"id": "ship", "label": "飞船", "required": true, "max_length": 80}
    ]
  }
}
```

每个非 `custom` 选项 ID 对应一个同名身份池，随机选择仅发生在所选池内；不能把“工程师”和“经理”等不同选项都指向一个无区分的默认身份池。身份池中的对象和定制身份均形成 `player_profile` 文本字段，例如 `name`、`role`、`ship`。每个身份必须有非空 `name`，且不得与 NPC 姓名冲突；模板用到的每个字段必须在所有可选身份中非空。若提供 `custom` 选项，模板引用的字段与 `name` 都必须声明为必填的 `custom_fields`，问题在上传校验阶段报告。

模板只接受 `{{name}}` 这样的简单变量：标识符以小写字母开头，只包含小写字母、数字和下划线，且必须出现在白名单中。平台不执行表达式、属性访问、下标、函数或模板代码；未知变量和不完整的双花括号会导致校验失败。替换只执行一次，身份字段中出现的花括号或类似代码的字符串会作为普通文本保留。

题材内容写在模板中，例如以下公开合成示例；年龄、大学或参加节目都不是平台默认身份：

| 题材 | 模板 | 身份字段示例 |
| --- | --- | --- |
| 恋综 | `你是{{name}}，是应邀参加节目的大学生。` | `name=艾然` |
| 奇幻 | `你是{{name}}，来自{{realm}}的{{role}}。` | `name=艾然, realm=星谷, role=法师` |
| 悬疑 | `你是{{name}}，调查{{case}}的{{role}}。` | `name=艾然, case=失窃案, role=侦探` |
| 职场 | `你是{{name}}，作为{{role}}进入{{company}}。` | `name=艾然, role=设计师, company=青石公司` |

兼容规则：旧蓝本缺少新增字段时仍可加载，旧存档仍读取原包与原序章。只有一个非定制选项的旧包仍可沿用平铺的 `player_profiles`，没有身份模板时使用中性的“你是姓名……”介绍，并仅按已提供的年龄、学校、专业补充文字。旧包若有多个非定制选项，却没有按 ID 分组的身份池，仍可加载并续玩已有存档；新建准备式开场与上传版本须补齐映射，避免忽略玩家选择。新增约束不放在全局加载器中拒绝所有旧包。

玩家可以尝试未在 `actions` 中列出的行动。`actions` 仅用于特殊的预设状态转换；重要物品或位置若需要被自由行动持续改变，可在 `manifest.json` 声明允许修改的**状态字段**，而不是列举所有动词。例如：

```json
{
  "initial_state": {
    "world": {"shop_window": {"broken": false}},
    "actors": {"player": {"location": "square"}}
  },
  "mutable_state": [
    {"path": ["world", "shop_window", "broken"], "values": [false, true]}
  ],
  "actions": []
}
```

上述 `mutable_state` 声明在当前唯一回合引擎 `single_call` 中仍受支持：模型提出行动效果时，运行时会按剧本声明的可写字段校验路径与取值。引擎会保存玩家行动、故事和角色各自获知的经历，但普通互动不要求模型写入物品状态或阶段状态。旧的 `multi_agent_beta` 执行流程已归档，当前配置不能选择该引擎。确定性的剧本事件仍可通过 `campaign.json` 的效果更新状态。预定剧情事件的条件可用 `when_path` 搭配单个 `when_value` 或多个 `when_values`。

上传包写入独立的 `STORY_UPLOAD_DIR`。数据库 `user_scenarios` 与 `user_scenario_versions` 记录作者、不可变包引用、版本和 SHA-256 内容指纹。上传新版本时保留旧版本，已有存档继续绑定原版本与指纹。同一剧本同时只允许一个待审提交；驳回或撤回后，作者上传新版本再提交。

每位作者最多保留 20 个剧本。未发布、未送审的草稿可删除；已发布或送审的剧本不能直接删除，以免已有存档和审核记录失去依赖。

## 存储边界

官方剧本可以在目录条目中配置可选的 `artwork`：`cover` 指向剧本包内的封面图片，`portraits` 将角色 ID 映射到剧本包内的肖像图片，例如 `"artwork": {"cover": "art/cover.png", "portraits": {"npc_a": "art/npc_a.png"}}`。图片仅允许 PNG、WebP 或 JPEG，并须保存在私有剧本目录中。API 经登录态提供封面；角色肖像只在该存档已呈现角色之后提供。公开仓库无需存放私有剧本图片。当前用户 ZIP 上传仍仅接受 JSON，暂不提供作者上传图片。

官方目录条目还可配置 `public_profiles`，将角色 ID 映射到玩家可见的简短人物介绍。它只在玩家已经遇见该角色后出现在人物卡；角色私有世界书、NPC 上下文压缩摘要不会直接返回给玩家。共同经历保存在已提交事件中。单次场景结果仅在发生值得回忆的互动时，给在场且直接参与的 NPC 留一条简短事实记忆；普通活动不额外提炼，也不为记忆再次调用模型。玩家保留该场景的完整正文。

`GameCatalog` 从 `ScenarioCatalogSource` 读取官方目录，并由 `ScenarioPackageStore` 定位发布包。用户上传包经 `PublishedPackageStore` 写入，当前实现为 `LocalPublishedPackageStore`。接口位于 `packages/platform/src/storyloop_platform/portal/scenario_storage.py`：

- `ScenarioCatalogSource.games()` 返回目录条目；包引用由服务端生成。
- `ScenarioPackageStore.materialize(reference)` 返回包含 manifest、世界书和可选 campaign 的本地目录。远端实现应在返回前完成原子缓存写入。
- `PublishedPackageStore.publish(reference, source)` 写入已验证的包；`remove(reference)` 清理数据库写入失败后的包。
- 取用存档时再次校验包 ID、版本与指纹；变更包内容需显式迁移。

元数据由 SQLite 或 PostgreSQL 管理，发布包使用本地持久化目录。后期可把发布包写入私有 OSS，并把读取实现改为本地缓存。当前代码未实现 OSS 上传、网页内逐步创作或玩家举报。

## 公开审核与权限

角色为普通玩家、审核员、管理员。权限在服务端按每次请求检查。审核员只能查看作者明确提交的固定版本，不能查看私有草稿或其他玩家存档。管理员可管理账号角色、停用账号、公开版本状态和审计记录。最后一个有效管理员不能被撤销或停用。

审核通过后，该版本进入公共目录。普通退场停止新存档，已有存档可继续；违规下架同时阻止公开旧存档继续进入。审核员可用独立存档试玩待审版本，最多 12 回合，平台承担模型费用，不扣玩家积分，也不提取玩家画像。管理员审核自己提交的剧本时，必须填写覆盖原因。审核与管理操作记录在 `management_audit`。
