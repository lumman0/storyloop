# 用户剧本与公开审核

官方剧本由部署者维护的 `catalog.json` 加载。登录用户可以在“我的剧本”上传 ZIP 剧本包。上传后是私有草稿；开启私有试玩后，仅作者账号可以在目录中看到。作者也可以把一个固定版本提交审核，通过后进入公共目录。其他玩家不能读取未送审的草稿或创建其存档。

## 上传格式与限制

ZIP 根目录需直接包含 `manifest.json` 和其中引用的世界书 JSON；章节剧本还需 `campaign.json`。文件名仅接受英文字母、数字、下划线和短横线，以 `.json` 结尾；不接受外层文件夹、非 JSON 文件、符号链接、重复文件名或不安全路径。压缩包最大 4 MiB，最多 16 个文件，单文件解压后最大 2 MiB，全部解压后最大 8 MiB。服务端使用 `ScenarioPackage` 和 `CampaignProgram` 校验，失败时不创建草稿。

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

自由行动会记录结果并投递给能感知的角色；裁决器只有在字段已声明且新值属于 `values` 时才能持久改变状态。没有声明的字段不会被模型直接写入。技术裁决失败不会提交行动或推进故事时间。

上传包写入独立的 `STORY_UPLOAD_DIR`。数据库 `user_scenarios` 与 `user_scenario_versions` 记录作者、不可变包引用、版本和 SHA-256 内容指纹。上传新版本时保留旧版本，已有存档继续绑定原版本与指纹。同一剧本同时只允许一个待审提交；驳回或撤回后，作者上传新版本再提交。

每位作者最多保留 20 个剧本。未发布、未送审的草稿可删除；已发布或送审的剧本不能直接删除，以免已有存档和审核记录失去依赖。

## 存储边界

`GameCatalog` 从 `ScenarioCatalogSource` 读取官方目录，并由 `ScenarioPackageStore` 定位发布包。用户上传包经 `PublishedPackageStore` 写入，当前实现为 `LocalPublishedPackageStore`。接口位于 `src/story_harness/portal/scenario_storage.py`：

- `ScenarioCatalogSource.games()` 返回目录条目；包引用由服务端生成。
- `ScenarioPackageStore.materialize(reference)` 返回包含 manifest、世界书和可选 campaign 的本地目录。远端实现应在返回前完成原子缓存写入。
- `PublishedPackageStore.publish(reference, source)` 写入已验证的包；`remove(reference)` 清理数据库写入失败后的包。
- 取用存档时再次校验包 ID、版本与指纹；变更包内容需显式迁移。

元数据由 SQLite 或 PostgreSQL 管理，发布包使用本地持久化目录。后期可把发布包写入私有 OSS，并把读取实现改为本地缓存。当前代码未实现 OSS 上传、网页内逐步创作或玩家举报。

## 公开审核与权限

角色为普通玩家、审核员、管理员。权限在服务端按每次请求检查。审核员只能查看作者明确提交的固定版本，不能查看私有草稿或其他玩家存档。管理员可管理账号角色、停用账号、公开版本状态和审计记录。最后一个有效管理员不能被撤销或停用。

审核通过后，该版本进入公共目录。普通退场停止新存档，已有存档可继续；违规下架同时阻止公开旧存档继续进入。审核员可用独立存档试玩待审版本，最多 12 回合，平台承担模型费用，不扣玩家积分，也不提取玩家画像。管理员审核自己提交的剧本时，必须填写覆盖原因。审核与管理操作记录在 `management_audit`。
