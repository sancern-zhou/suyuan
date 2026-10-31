# 广东运维语义注册中心

`registry.yaml` 是 Agent 解释指标结果的业务语义来源，登记数据集、粒度、适用范围、时间窗口、质量限制和关键指标的分子/分母。

不同工具按场景选择最小充分结果结构，规则见 `result_contract.yaml`。Cube 指标查询需要
`semantic_context`；不得为了字段统一返回空数组或重复的 `summary`。

- Cube schema 负责执行查询（`../cube/schema/*.js`），**同时是查询成员（measures/dimensions）
  的唯一真相源**——成员不进 schema 查询必失败，新增/改名成员必须改 schema；
- dbt 和 `../sync/datasets/*.yaml` 负责数据实现与字段契约；
- `gen_semantic_artifacts.py` 把 schema 成员与 `registry.yaml` 业务语义 join 成
  `backend/app/tools/query/guangdong_cube_metrics/catalog.generated.json`，
  `guangdong_query_metrics` 运行时 fail-closed 加载该产物（缺失/损坏拒绝启动），
  成员白名单、`describe_cube` 与 `semantic_context` 全部来自它；
- 修改指标口径后运行 `python validate_registry.py`，并同步更新对应 Cube、dbt 和数据集契约；
- AI 编程维护或提交前运行 `python gen_semantic_artifacts.py --check`，检查
  `catalog.generated.json` 与 Cube 目录、注册表是否漂移（dq_check 每日亦核对）；
  需要更新时先运行不带 `--check` 的命令，再审阅生成差异；
- 业务限制、分子/分母和适用范围仍以 `registry.yaml` 人工维护内容为准（精选登记，
  未登记成员的说明以 schema title 为准）；backend 不再持有手工成员目录
  （2026-10-31 起，旧 `catalog.generated.yaml` 审查索引废弃，审查走 git diff JSON 产物）。

DQ 状态来源：`../sync/dq_check.py` 每日写入 `guangdong_sync.dq_results`；
`guangdong_query_metrics` 按表读取最新检查生成 `quality_status`
（FAIL→blocked / WARN→degraded / 全 OK→ok / 无记录→unknown）。

当 DQ 状态为 `blocked` 或 `degraded` 时，Agent 应在结论中明确说明质量影响；
分母为零时应回答"不可评估"，不能转换成 0%（如部分工单类型无计划完成时间时，超期率不可评估）。
