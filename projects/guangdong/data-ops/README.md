# guangdong-ops data-ops（广东运维数据链路源码）

广东运维数据链路三层（模式对齐江苏 `projects/jiangsu-ops/data-ops/`，2026-10-24 自
fetcher 方式迁移而来，worker 内不再运行任何工单同步 fetcher）：

```
data-ops/
├── sync/    ODS 同步层 — 源 SQL Server（Operation_SC_GD, 172.20.105.179）→ 本机 PostgreSQL
│            guangdong_ods（sync_table.py 引擎）。datasets/*.yaml 是查询契约唯一人工维护源
│            （gen_tool_contract.py 生成后端工具 contract.txt）。
├── dbt/     mart 加工层 — guangdong_ods → guangdong_mart（6 个模型 / schema 数据测试）。
│            sync-all = tag:frequent（小时级）；sync-daily = tag:daily（每日 02:30）。
├── cube/    语义层 — Cube Core 0.35.x，口径唯一定义在 schema/*.js（同时是查询成员
│            唯一真相源），REST 127.0.0.1:4611（江苏为 4610，同机共存错开端口）。
└── semantic/ 语义注册中心 — registry.yaml 登记指标业务口径（分子/分母/粒度/适用范围/
             限制，精选维护）；gen_semantic_artifacts.py 把 schema 成员与 registry join 成
             backend 工具加载的 catalog.generated.json 并做漂移检测（dq_check 每日核对）；
             validate_registry.py 提交前语义校验。
```

## 数据流

```
Operation_SC_GD（dbo.working_orders / working_order_details / wo_commonfile_links /
                 base_station / base_device 兼容视图）
  --(sync_table.py, 水位增量)--> guangdong_ods
  --(dbt build)--> guangdong_mart（working_orders / working_order_details /
                   wo_commonfile_links / dim_station / dim_device /
                   mart_work_order_analysis）
  --(受控SQL工具 execute_guangdong_mart_sql)--> Agent 字段级取证
  --(Cube REST + guangdong_query_metrics)--> Agent 指标点查（口径唯一）
```

## 与 fetcher 方式的差异（迁移说明）

| | 旧（fetcher） | 新（data-ops） |
|---|---|---|
| 同步执行者 | backend worker 内 `guangdong_work_order_fetcher`（每小时 :40） | 运行时计划任务 `sync-all.cmd`（小时级）+ `sync-daily.cmd`（02:30） |
| 层次 | 源 → guangdong_mart 直写 | 源 → guangdong_ods →（dbt）→ guangdong_mart |
| 加工能力 | 无（明细即宽表） | dbt：列名契约映射、`mart_work_order_analysis` 预计算宽表、数据测试、原子重建、自动 GRANT |
| 语义治理 | contract.txt + 文档 + 提示词 | 三者之上再加 Cube 语义层 + registry.yaml + 结果契约 + DQ 质量门（`guangdong_sync.dq_results`） |
| 水位 | `guangdong_sync.sync_watermark`（dataset 结构） | `guangdong_sync.ods_sync_watermark`（table 结构）；旧表保留只读兜底，迁移完成后可清理 |

## 与运行时目录的关系

**本目录是代码源（进 git）；运行时目录（本机为 `M:\suyuan-tools\data-ops-guangdong`）含真实凭据、
logs、target、node_modules 和计划任务入口。** 改代码流程：改本目录 → 同步到运行时 →
按需重启（dbt 改动随下次调度生效；cube 改动需重启 Cube 服务）。

计划任务（Windows schtasks，部署时注册）：
- `SuyuanGuangdong-SyncAll`：每小时运行 `sync\sync-all.cmd`
- `SuyuanGuangdong-SyncDaily`：每日 02:30 运行 `sync\sync-daily.cmd`
- `SuyuanGuangdong-Cube`：开机自启常驻 `cube`（`node index.js`，127.0.0.1:4611）

.cmd 文件保持纯 ASCII（GBK 代码页控制台下 UTF-8 中文注释会破坏执行）。

## 首次部署 / 从 fetcher 切换（cutover）

1. 运行时目录准备：复制本目录 → 填 `sync/sync_config.json`（模板 `sync_config.example.json`）、
   `dbt/profiles.yml`（模板 `profiles.yml.example`）、`cube/local.json`（模板 `local.example.json`）。
2. 建库建角色：`psql -v agent_reader_password=... -f sync/setup_agent_guardrails.sql`
   （幂等：agent_reader 只读角色 + query_audit 补列 + dq_results）。
3. 首拉：`sync_table.py <table>` 逐表执行（工单三表按今年窗口 `{year_start}-01-01` 回填，
   每年 1 月自动滚动；静态维表全量）。
4. dbt 初始化：`dbt build`（全量建 guangdong_mart 六表；与旧 fetcher 表同名接管，
   dbt 重建为原子换名，消费者无感；新增 refreshed_at / mart_work_order_analysis）。
5. 核对：`sync_table.py <table> --check` 行数对账 + `dq_check.py` 全绿；
   抽查 mart 行数与旧表一致后停用旧 fetcher 计划（代码已删除 fetcher，重启 worker 即生效）。
6. 注册计划任务（上节），观察一个同步周期。

回滚：旧 fetcher 代码在 git 历史（删除于 2026-10-24），恢复文件并重启 worker 即可；
data-ops 链路写入与 fetcher 同名表，回滚后仍可运行。

## 凭据策略（全部不进 git，模板随仓库）

| 文件 | 内容 | 模板 |
|---|---|---|
| `dbt/profiles.yml` | 目标库（suyuan_guangdong）密码 | `dbt/profiles.yml.example` |
| `sync/sync_config.json` | 源库 + 目标库凭据、全量表清单 | `sync/sync_config.example.json` |
| `cube/local.json` | Cube JWT 签名密钥、agent_reader 密码 | `cube/local.example.json` |

后端 `.env` 仍需：`OPS_SQLSERVER_*`（execute_ops_sql_query 直查源库核对实时状态）、
`OPS_MART_DATABASE_URL`（mart 查询/审计/DQ 连接）、`CUBE_API_URL`/`CUBE_API_SECRET`
（语义层 REST，默认 `http://127.0.0.1:4611/cubejs-api/v1`）。

## ODS 兜底通道（同步的数据不允许 Agent 查不到）

主契约 `contract.txt`（37 张：高频维度/指标完整字段说明 + 长尾一句话）覆盖不到的
同步表（月检 `rf_m_*`、质控 `rf_q_*`、半年 `rf_hy_*`、年维保 `rf_y_*`、
组分网浊度计、现场检查评分 `sec_checkscore*` 等 53 张）由
`backend/app/tools/query/guangdong_ops_sql_query/ods_contract.txt` 托底：
`execute_guangdong_mart_sql` 一个工具两套白名单，兜底表引用写全限定名
`guangdong_ods.<表名>`，一句话索引 + `describe_table` 取列（同步内部列 `_synced_at` 等不外露）。

- 生成：`gen_ods_fallback_contract.py`（清单 = sources.yml 声明 − 契约覆盖 + EXTRA_FALLBACK，
  新表缺用途登记直接生成失败）；`--grant` 给 agent_reader 补授权。
- 校验：`dq_check.py` 第 6 项每日查生成物漂移与授权完整性；
  `audit_ods_coverage.py` 随时人工复核库面（GAP/未声明表必须为 0，退出码非 0 即有缺口）。

## 口径修改的正确姿势（四方一致）

1. 改 `sync/datasets/*.yaml`（契约）
2. 同步改 `dbt/models/*.sql`（实现）
3. 同步改 `cube/schema/*.js`（语义执行）
4. 同步改 `backend/app/tools/query/guangdong_cube_metrics/tool.py` 的 CATALOG（工具目录）

提交前：

```bash
PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_tool_contract.py --check
PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_ods_fallback_contract.py --check
python projects/guangdong/data-ops/semantic/validate_registry.py
python projects/guangdong/data-ops/semantic/gen_semantic_artifacts.py --check
python projects/guangdong/data-ops/sync/dq_check.py   # 运行时环境
```

业务语义字典（工单类型、故障原因、站点网络）见 `../docs/work-order-semantics/`；
运维模式提示词的口径展示见 `../prompts/ops.md`。
