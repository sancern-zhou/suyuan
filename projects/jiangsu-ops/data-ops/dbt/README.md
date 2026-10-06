# jiangsu_marts — 江苏运维 mart 层 dbt 项目

## 这是什么

ODS → mart/dim 加工层的 dbt 化重建（2026-10-02 起），替代原 `sync/mart_*.sql` + `dim_*.sql` 的
psql 脚本序列。抽数（SQL Server → jiangsu_ods）仍由 `sync/sync_table.py` 负责，dbt 只管
加工：建模、依赖排序、原子换名重建、数据测试、字典表变更快照。

## 目录

- `dbt_project.yml` — 项目配置；tag:frequent = 5分钟链路，tag:daily = 每日链路
- `profiles.yml` — 连接 suyuan_jiangsu 库（schema jiangsu_mart）
- `models/` — 11 个模型（2 dim + 9 mart），每个自带 GRANT agent_reader 的 post_hook
- `models/sources.yml`、`models/schema.yml`、`snapshots/*.sql` — **生成物**，
  由 `../sync/gen_dbt_artifacts.py` 从契约（datasets/*.yaml + sync_config.json）派生，勿手改
- `snapshots/` — 19 张字典/规则表的每日 check 快照（SCD2），落在 `jiangsu_snapshot` schema，
  不对 agent 开放；alm_rule 无更新时间列，靠整行哈希判变

## 常用命令

```cmd
cd /d E:\Tools\suyuan-jiangsu\dbt
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe debug
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --no-use-colors          # 全部模型+测试
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --select tag:frequent+ --no-use-colors
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --select tag:daily+ --no-use-colors
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe snapshot --no-use-colors
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe source freshness --no-use-colors
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe docs generate && dbt docs serve  # 血缘文档
```

## 与同步任务的接线

- `sync-all.cmd`（5分钟）：ODS 增量 → `dbt build --select tag:frequent+`
- `sync-daily.cmd`（02:30）：ODS 字典全量 → `dbt snapshot` → `dbt build --select tag:daily+`
  → 对账 → dq_check（dq_check 继续负责 watermark 心跳/新鲜度/契约漂移）

## 修改口径的正确姿势

1. 改 `sync/datasets/*.yaml`（契约单一事实源）
2. 改对应 `models/*.sql`
3. 跑 `python sync/gen_dbt_artifacts.py`（重新生成 sources/schema/snapshots）
4. 跑 `python sync/gen_tool_contract.py`（Agent 工具契约）+ 重启后端

## 查上游字典表变更历史

```sql
select * from jiangsu_snapshot.alm_rule
where dbt_valid_to is not null order by dbt_valid_from desc;
```
