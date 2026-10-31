# 广东数据语义图谱上线与运维手册

覆盖两块图谱资产的落地与维护：**数据语义图谱**（确定性种子，第一期）与**运维知识图谱**
（LLM 抽取，第二期）。框架与检索由共享层提供（`backend/app/knowledge_base/`），本手册只讲
广东分支的部署动作与日常维护。

## 一、数据语义图谱（确定性种子）

### 内容与来源

| 资产 | 来源（单一真相） | 说明 |
| --- | --- | --- |
| 7 个数据域、42 张契约表、108 条关系 | `data-ops/sync/datasets/*.yaml` | 生成物：`data-ops/graph/graph_seed.json` + `data-ops/graph/广东数据语义契约.md` |
| 24 个指标口径（含分子分母血缘） | `data-ops/semantic/registry.yaml` | 同名指标按 cube 前缀消歧（工单超期率/巡检超期率） |
| 6 个查询路由工具（策展别名） | `gen_graph_seed.py` 内 `QUERY_TOOLS` | 改动须同步 `prompts/gd_query.md` 数据路由节 |
| 站点台账（约 432 站/地市/运维单位） | 运行时 `dim_station`（站点目录缓存） | 同步时由 `station_seed.py` 并入，不入提交的种子 JSON |

### 上线步骤（部署环境执行一次）

```bash
cd /home/<部署目录>/backend
# 1. 重新生成种子产物（源 yaml mtime 变化后会漂移，dq_check 会提醒）
PYTHONPATH=. python ../projects/guangdong/data-ops/sync/gen_graph_seed.py
# 2. 建库 + 上传契约文档 + 清图 + 确定性写入（含站点台账）
PYTHONPATH=. python ../projects/guangdong/data-ops/sync/graph_seed_sync.py --ensure-kb
```

- 建库动作创建名为 `广东数据语义` 的图谱知识库（`knowledge.bindings.data_semantics`）。
- 项目已声明 `knowledge.graph_entry_modes: [gd_query, query]`，重启 web/worker 后问数入口
  自动做图谱实体链接；命中情况查日志事件 `graph_entry_hit` / `graph_entry_miss`。

### 日常维护

- `datasets/*.yaml` 或 `registry.yaml` 变更后：运行 `gen_graph_seed.py` 重新生成 → 重跑
  `graph_seed_sync.py`（自动替换文档、清图重建）。`dq_check.py` 的 `graph_seed` 检查项会在
  漂移时 FAIL，不重跑种子不阻塞问数，但图谱口径会滞后。
- 站点台账变化：重跑 `graph_seed_sync.py`（不加参数也会按当前站点目录刷新站点实体）。
- 图谱抽取运行记录在 `knowledge_graph_extraction_runs`（`prompt_version=guangdong_data_semantics_seed_v1`，
  `model_name=deterministic`），可与 LLM 抽取的运行记录区分审计。

## 二、运维知识图谱（LLM 抽取，第二期）

目标知识库：`广东运维工单知识`（绑定 `knowledge.bindings.station_fault_diagnosis`，故障诊断
定时任务 `gd_fault_diagnosis_watch` 已在用 `knowledge_graph_query`）。素材：

- `docs/work-order-semantics/01~04`：工单类型与流程字典、故障原因与诊断路径、站点网络与数据集、
  故障处置经验归纳。
- `docs/sup-instrument-rules/01~06`：组分站表单语义与审核规则。

### 抽取流程

1. 确认知识库已存在且 `graph_enabled`；如未入库，先把上述文档上传到该知识库
   （知识库管理页上传即可）。
2. 触发图谱构建（管理接口）：
   `POST /knowledge-bases/{kb_id}/graph/build`，`mode=reset_and_build`（全量重建）或
   `mode=pending`（只处理新文档）。进度查询 `GET /knowledge-bases/{kb_id}/graph/build/{task_id}`。
3. LLM 抽取产物初始为 `candidate`，检索只用 `confirmed/published`：在知识库图谱面板人工审核
   （合并重复实体、修正关系、确认状态），或用图谱编辑模式批量处理。
4. 抽取质量抽检用共享层评估脚本（金标 JSONL，见根目录 `docs/knowledge-base-graph-operations.md`
   的「离线质量评估」节）：`python scripts/evaluate_scene_graph.py --kb-id <kb_id> --gold-jsonl ...`。

### 与数据语义图谱的边界

- 运维知识库的实体（Symptom→Component→Cause、规则）来自文档抽取，供故障诊断与知识问答；
  数据语义库的实体（指标/表/工具/站点）来自管道种子，供问数入口链接。两库各自绑定，不混库。
- 故障诊断模式同时持有两库能力：`station_fault_diagnosis` 白名单内 `knowledge_graph_query`
  按会话选择的知识库检索；定时任务按 `knowledge_base_binding` 注入运维工单知识库。

## 三、验证清单

- [ ] `graph_seed_sync.py` 输出 entities ≥ 79（种子）+ 站点台账数，relations 对应增长。
- [ ] 问「工单超期率怎么算」：gd_query 回复出现口径与语义层路由（日志有 `graph_entry_hit`）。
- [ ] 问「华工大站属于哪个运维单位」：命中站点实体与 `managed_by` 关系。
- [ ] 问「广州有哪些组分站」：命中地市/组分站实体（组分站缺口如实声明）。
- [ ] `dq_check.py` 的 `graph_seed` 检查项 OK。
- [ ] 故障诊断定时任务 `gd_fault_diagnosis_watch` 的图谱检索返回运维工单知识库内容。
