# jiangsu-ops data-ops（江苏运维数据链路源码）

江苏运维数据链路三层的代码源，随 `suyuan` 主仓库跟踪：

```
data-ops/
├── sync/    ODS 同步层 — 源 SQL Server → 本机 PostgreSQL jiangsu_ods（sync_table.py 引擎）
│              datasets/*.yaml 是查询契约唯一人工维护源（gen_tool_contract.py 生成后端工具 contract.txt）
├── dbt/     mart 加工层 — jiangsu_ods → jiangsu_mart（19 个模型 / 21 字典 SCD2 快照 / schema 数据测试）
│              sync-all = tag:frequent；sync-daily = snapshot + tag:daily
└── cube/    语义层 — Cube Core 0.35.x，口径唯一定义在 schema/*.js，REST 127.0.0.1:4610
```

语义注册中心位于 `semantic/registry.yaml`，登记指标定义、分子/分母、粒度、适用范围和限制；
查询工具返回的 `semantic_context` 由此生成。提交前运行：

```cmd
python semantic\validate_registry.py
```

## 与运行时目录的关系

**本目录是代码源（进 git）；`E:\Tools\suyuan-jiangsu` 是服务器运行时**（含真实凭据、
logs、target、node_modules、计划任务入口 start-*.cmd / sync-*.cmd）。

改代码的正确流程：改本目录 → `deploy-to-runtime.cmd` 同步到运行时 → 按需重启
（dbt 改动随下次调度生效；cube 改动需重启 SuyuanJiangsu-Cube 任务）。

注意 deploy 脚本只新增/覆盖、不删除运行时文件；从仓库删掉的文件需手工去运行时目录清理。

## 凭据策略（全部不进 git，模板随仓库）

| 文件 | 内容 | 模板 |
|---|---|---|
| `dbt/profiles.yml` | 目标库（suyuan）密码 | `dbt/profiles.yml.example` |
| `sync/sync_config.json` | 源库 + 目标库凭据、全量表清单 | `sync/sync_config.example.json` |
| `cube/local.json` | Cube JWT 签名密钥、agent_reader 密码 | `cube/local.example.json` |

临时诊断脚本通过 `sync/_creds.py` 从 sync_config.json 取源库连接；cube 通过
`local.json`（或环境变量 `CUBEJS_API_SECRET` / `AGENT_READER_PASSWORD`）取密钥。
`setup_agent_guardrails.sql` 的角色密码用 `psql -v agent_reader_password=...` 传入。

## 生产入口（服务器侧）

- 计划任务 `SuyuanJiangsu-*`（sync-all / sync-daily / sync-env-hourly / sync-mart / Cube 等，360 安全卫士
  白名单必须覆盖，否则会被静默删除——见 2026-09-24 事故）
- dbt：`sync-all.cmd`（tag:frequent 全量链路）/ `sync-daily.cmd`（SCD2 快照 + tag:daily）
- 站房动环小时分片：`sync-env-hourly.cmd`（每小时第 10 分钟, integrated_h_<年>_<站> 增量;
  智能事件/工单审核动环证据统一读该同步链路, API 故障日兜底副本滞后至多 1 小时）
- Cube：`start-cube.cmd` → 127.0.0.1:4610，`gen-token.js` 生成调用 JWT
- 护栏/审计：`sync/setup_agent_guardrails.sql`（agent_reader 只读 + query_audit 审计表）
