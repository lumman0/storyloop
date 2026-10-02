# 用户剧本上传与后续创作

官方剧本继续由部署者维护的 `catalog.json` 加载。登录用户现在可以在“我的剧本”上传 ZIP 剧本包，上传后先成为私有草稿；作者发布后，仅作者账号可在目录中看到并试玩。其他玩家不能读取、发布或创建该剧本的存档。网页内逐步编辑剧本和公开发布仍是后续功能。

## 上传格式与限制

ZIP 根目录需直接包含 `manifest.json` 和其中引用的世界书 JSON；章节剧本还需 `campaign.json`。文件名仅接受英文字母、数字、下划线和短横线，以 `.json` 结尾；不接受外层文件夹、非 JSON 文件、符号链接、重复文件名或不安全路径。压缩包最大 4 MiB，最多 16 个文件，单文件解压后最大 2 MiB，全部解压后最大 8 MiB。服务端会使用现有 `ScenarioPackage` 和 `CampaignProgram` 规则校验；失败时保留具体错误，不创建草稿。

上传包写入独立的 `STORY_UPLOAD_DIR`。数据库 `user_scenarios` 与 `user_scenario_versions` 记录作者、私有可见性、不可变的包引用、版本和指纹。发布不会修改包内容。现阶段一次上传生成一个草稿和一个版本；后续编辑和发布新版本时仍应保留旧版本，供已有存档恢复。

每个作者最多保留 20 个剧本。未发布的草稿可由作者删除并释放名额；已发布剧本不能直接删除，以免已有存档失去依赖的包。

## 剧本存储边界

现阶段 `GameCatalog.load(path)` 使用 `LocalScenarioCatalogSource` 读取官方目录 JSON，使用 `LocalScenarioPackageStore` 解析其中的 `package` 路径。`PlayerPortal` 默认保持这个本地部署方式，也可注入由 `GameCatalog.from_sources(catalog_source, package_store)` 创建的目录。用户上传包通过 `PublishedPackageStore` 写入，当前实现为 `LocalPublishedPackageStore`。这些接口定义在 `src/story_harness/portal/scenario_storage.py`：

- `ScenarioCatalogSource.games()` 返回与现有 `games` 数组相同的条目；`package` 是不透明的发布包引用，不应来自玩家直接提交的路径。
- `ScenarioPackageStore.materialize(reference)` 返回已准备好的本地目录，包含 `manifest.json`、世界书及可选的 `campaign.json`。远端实现需要把不可变对象下载到本地缓存，并在返回前完成原子写入。
- `PublishedPackageStore.publish(reference, source)` 写入已验证的包，`remove(reference)` 清理数据库写入失败后的包。引用由服务端生成，不能使用玩家上传的文件名。
- `GameCatalog` 读取包时校验剧本格式并计算 SHA-256 指纹；再次取用时重新定位和校验。存档继续保存 package ID、version、hash，内容发生变化时拒绝继续使用。

当前用户剧本的元数据已经由 SQLite 或 PostgreSQL 管理，发布包仍使用本地持久化目录。后期可把发布包写入私有 OSS，并把读取实现改为本地缓存；账号、剧本归属、发布版本与存档继续留在数据库。当前代码尚未实现 OSS 上传、网页内逐步创作或公开发布审核。

后续把“创作草稿”和“可游玩版本”进一步分开：

1. 增加网页内逐步编辑角色、公开世界设定、初始状态和剧情节点，自动保存私有草稿。
2. 支持将改动发布为同一剧本的新版本，旧存档固定到原版本和内容指纹。
3. 公开发布前加入内容审核、举报和下架流程；公开目录按可见范围过滤。

用户上传目录不应直接挂进公开的官方目录，也不应向浏览器发送完整剧本包。
