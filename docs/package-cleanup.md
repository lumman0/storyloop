# 剧本包一致性检查与清理重试

适用迁移：`0013_package_cleanup`。先按部署流程备份并完成数据库迁移；本命令不会自动迁移，也不会扫描其他工作树。

从仓库根目录执行，只读检查既有 SQLite 数据库和上传目录：

```sh
python -m story_harness.cli.package_cleanup --db /path/to/game.sqlite3 --uploads /path/to/uploaded-scenarios
```

PostgreSQL 使用显式的 `DATABASE_URL` 环境变量并省略 `--db`。必须确认该库和 `--uploads` 属于同一实例；数据库地址不放在命令参数或报告中。

默认输出 `pending`、`missing_manifests`、`untracked_packages`、`invalid_references`，只报告不删除。`untracked_packages` 可能是尚未完成入库的上传，不可仅凭此列表判断为垃圾。清单仅核对本地包引用与 manifest 是否存在，不代替内容哈希或完整备份验证。

需要处理已删除草稿遗留文件时，在同一命令增加 `--retry-queued`。每批最多处理 100 条已落库的删除意图，重新检查 `user_scenario_versions` 引用；没有队列意图的文件不会删除。仍有引用时保留记录并返回 `referenced`，文件操作失败时返回 `retry_pending`、保留尝试次数和错误类型，成功后移除队列记录。

命令退出 0 表示本次操作执行完成，并不表示队列已清空；应查看返回状态和 `pending`。数据库不可用或缺少迁移时退出 1。暂不设置定时自动清理，避免把巡检发现自动升级为删除授权。
