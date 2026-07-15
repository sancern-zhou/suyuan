# 社交绑定数据库结构修复设计

## 背景与根因

`aa55c2f` 为 `social_users` 模型增加了 `platform_user_id`、`platform_username`、
`platform_display_name`、`account_id` 和 `ilink_user_id`，并新增了
`007_add_platform_social_bindings.sql`。运行中的 PostgreSQL 仍保留旧版
`social_users` 结构。

启动时调用的 `Base.metadata.create_all()` 只能创建缺失的表和索引，不能给已有表
增加字段。项目也没有执行 `backend/app/db/migrations/*.sql` 的通用启动迁移器。因此
`weixin_scan_tasks` 能由 `create_all()` 新建，而 `social_users` 的五个新增字段和两个
条件唯一索引没有落库。消息路由查询 ORM 模型时会选择全部模型字段，最终触发
`UndefinedColumnError`。

## 修复目标

- 立即将当前数据库安全升级到 `007` 所要求的结构，恢复微信消息路由。
- 后续部署和服务重启能够幂等补齐社交绑定结构，不再依赖人工记住执行 `007`。
- 保留已有 `social_users` 数据，不自动绑定或迁移旧微信身份。
- 不在本次修复中引入完整的数据库版本管理框架。

## 方案

采用“现库执行已有迁移 + 启动兼容迁移”方案。

### 当前数据库恢复

使用现有 `007_add_platform_social_bindings.sql` 的等价 DDL，在同一事务中执行：

1. 给 `social_users` 幂等增加五个可空字段。
2. 幂等确保 `weixin_scan_tasks` 表和任务所有者索引存在。
3. 幂等创建活动平台用户、活动微信用户两个条件唯一索引。
4. 幂等创建活动账号查询索引。

所有新增字段均可空，不回填旧记录；已有社交用户不会被误认为已绑定平台用户。
迁移失败时事务整体回滚，并输出不含凭据的错误。

### 启动兼容迁移

在 `app.db.database.init_db()` 中，继 `Base.metadata.create_all()` 后调用专用的
`_ensure_social_binding_schema()`。该函数只在 PostgreSQL 上执行与 `007` 等价的
幂等 DDL，并复用当前启动事务。

本次采用专用兼容函数，而不实现自动扫描 SQL 文件：现有迁移文件并非统一版本体系，
部分包含显式事务和数据回填，启动时盲目扫描执行会扩大风险。专用函数与项目已有的
`_ensure_uploaded_files_schema()` 模式一致，变更范围可控。

若兼容迁移失败，`init_db()` 必须失败，不能记录成功后继续启动数据库依赖功能。
现有生命周期层会记录 `database_initialization_failed`，便于部署侧发现结构问题。

## 数据流

```text
服务启动
  -> create_all() 创建缺失表
  -> ensure social binding schema 补齐已有 social_users
  -> 提交启动事务
  -> 微信消息按 bot_account + ilink_user_id 查询有效绑定
  -> 找到 platform_user_id 后进入 Agent 路由
```

当前数据库会在代码部署前单独执行同一组 DDL，使正在运行的旧进程下一条消息查询即可
使用新字段；代码中的启动兼容迁移负责后续部署的一致性。

## 测试策略

先增加失败测试，再实现生产代码：

- PostgreSQL 兼容 DDL包含五个 `ADD COLUMN IF NOT EXISTS`。
- 兼容 DDL包含三个预期索引，其中两个保持 `status = 'active'` 的条件唯一约束。
- `init_db()` 在 `create_all()` 之后调用社交结构兼容函数。
- 非 PostgreSQL 方言明确跳过该兼容迁移，避免测试环境执行不支持的 DDL。
- 现有社交绑定、扫码归属和数据库测试继续通过。

数据库恢复后，通过 `information_schema.columns` 和 `pg_indexes` 只读校验字段与索引；
随后调用一次 `resolve_sender()` 查询路径，确认不再出现缺字段异常。是否能返回绑定取决于
用户是否已完成新版扫码，未绑定时返回空记录是正确行为。

## 验收标准

- 当前数据库 `social_users` 存在五个新增字段。
- 当前数据库存在 `uq_social_users_active_platform_user`、
  `uq_social_users_active_ilink_user` 和 `idx_social_users_active_account`。
- 微信入站消息不再抛出 `UndefinedColumnError`。
- 重复运行迁移或重复启动服务不会报对象已存在，也不会修改旧社交用户的绑定归属。
- 相关自动化测试在 `/root/miniconda3/envs/backend_py311` 环境通过。
