# 广东分支共享层欠账清单

> 2026-11-17 盘点。project/guangdong 相对 main 的共享路径内容分叉共 **17 个提交、286 文件、约 3.4 万行**（自 2026-10-30 `428d8608` 起）。按 AGENTS.md"共享层文件不得长期单侧演化"要求登记，分批处理。

## 已回合 main

| main 提交 | 内容 |
|---|---|
| `95cfed65` | write_file 路径契约错误信息指引 + preview 刷新 to_thread + 复盘技能口径说明 |
| `e5a5d8ce` | 机制层 15 文件：复盘 task_id/rule_prefix 分口径、孤儿复核转人工核验、artifact_readability 契约、面板台账补记 rf_table/brand、ocr 网关会话头、对应共享测试（82 项通过） |

## 待处理分类

### A. 广东业务内容——应迁带项目名路径或维持项目分支单侧

不回合 main（回合属于错误归属，main 是风清气智等共享部署基座）：

- `backend/app/tools/query/query_gd_suncere/**`（~8000 行，广东运维平台 API 取数工具）
- `backend/app/tools/query/guangdong_cube_metrics/**`、`guangdong_ops_sql_query/**`
- `backend/app/services/gd_suncere_api_client.py`（903 行）
- `backend/app/services/ops_work_order_audit_local.py`（广东本地化取数 T-SQL→PG）及 `_local_sup_test.py`
- `backend/app/services/ops_audit/configs/**`（sup_form_profiles 3419 行、rf_range_profiles、rule_catalog 等）
- `backend/app/services/ops_audit/rules/sup_*`（组分站规则 1624 行）及 rf_* 规则的业务改动
- `backend/app/services/ops_audit/rf_form_names.py` 后续新增内容、`utils/sup_audit_weekly_board.py`、`utils/component_semantics.py`
- VOCs/PM2.5 组分工具（`get_vocs_species`、`get_pm25_ionic` 等广东组分监测）
- `backend/app/services/station_operation_monitor/**`（AGENTS.md 存量豁免）

**迁移方向**：若后续其他项目要复用，先提炼为共享引擎提交 main（含文案配置化）；否则按判定准则迁 `tools/guangdong/**` 等带项目名路径。

### B. 平台特性——需逐项评估后回合

代码在共享路径、由广东需求驱动但具备跨项目价值的改动（约 1500 行）：

- `auth/operation_access.py`(331)、`auth/middleware.py`(59)、`auth/operation_client.py`(110)、`auth/routes.py`(129/10)、`lifecycle/operation_access.py`(55)——认证会话令牌与方法覆盖中间件（`11bbfe64`）
- `social/assistant_wakeup.py`(418)、`social/assistant_runs.py`(56)——助手唤醒/运行快照
- `db/sync_bridge.py`(91/30)、`agent/runtime/*`、`agent/workflow/delegation.py`(57/26)、`api/agent.py`(123/11)
- `agent/prompts/tool_registry.py`(93/12)——**注意含广东工具注册块，回合前须拆分（参照"混合文件项目专属注册块只出现一次"约束，main 曾因重复注册崩溃）**
- `utils/query_window_limits.py`(129)、`utils/async_cleanup.py`(65)、`utils/vocs_api_client.py`(206/13)、`utils/particulate_api_client.py`(97)
- `tests/core/test_async_no_blocking_calls.py`——守门测试本身未在 main，回合时需同步梳理 `ALLOWED_FILES` 豁免表
- 小修：`llm_concurrency`、`llm_failover`、`lifecycle_manager`、`font_utils`、`curated_facts`、`project_config/loader`

### C. 行为变更风险点——回合前必须确认其他项目不受影响

- `53f84f8c` 在共享路径退役流程/生命周期/设备一致性规则（删 `workflow_rules.py`、`lifecycle_rules.py`、`device_consistency_rules.py` 及对应测试/词表/统计字段）。main 与其他项目分支若仍依赖这些规则，回合即行为变更。
- `enable_visual` 默认值 True→False 翻转（`ops_work_order_audit/tool.py`）——改变所有项目审核默认行为。
- 审核窗口业务口径（周一锚点 + order_statuses 扩展，`audit_window.py` + `config.py`）。

## 回合操作记录（2026-11-17 机制层）

- 整文件回合 9 个（retrospective_stats / feedback_ledger / review_artifacts / semantic×2 / retro tool / human_feedback_routes / 测试×2），merge 后与 main 完全一致。
- 选择性回合 3 个（rule_engine 只取 readability 契约、final_issue_list 只取 orphan 机制保留 RF_REQUIRED_FIELD_LOW_VALUE 特判、ops 工具只取描述红线），main 与项目分支保留设计内差异。
- merge 冲突 2 处均取项目分支版（`final_issue_list.py`、`test_ops_audit_final_issue_list.py`——项目分支含 orphan 机制及规则配套，为超集）。
- 回归：main 82 项机制测试通过；项目分支 105 项通过。
