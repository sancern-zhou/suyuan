# 广东运维语义注册中心

`registry.yaml` 是 Agent 解释指标结果的业务语义来源，登记数据集、粒度、适用范围、时间窗口、质量限制和关键指标的分子/分母。

不同工具按场景选择最小充分结果结构，规则见 `result_contract.yaml`。Cube 指标查询需要
`semantic_context`；不得为了字段统一返回空数组或重复的 `summary`。

- Cube schema 负责执行查询（`../cube/schema/*.js`）；
- dbt 和 `../sync/datasets/*.yaml` 负责数据实现与字段契约；
- `guangdong_query_metrics` 从注册中心返回 `semantic_context`，包括指标定义、数据时点和 DQ 状态；
- 修改指标口径后运行 `python validate_registry.py`，并同步更新对应 Cube、dbt 和数据集契约；
- AI 编程维护或提交前运行 `python gen_semantic_artifacts.py --check`，检查 Cube 目录、
  注册表与生成索引是否漂移；需要更新时先运行不带 `--check` 的命令，再审阅生成差异；
- `catalog.generated.yaml` 是面向维护和审查的生成索引，不是新的业务语义来源；业务限制、
  分子/分母和适用范围仍以 `registry.yaml` 人工维护内容为准。

DQ 状态来源：`../sync/dq_check.py` 每日写入 `guangdong_sync.dq_results`；
`guangdong_query_metrics` 按表读取最新检查生成 `quality_status`
（FAIL→blocked / WARN→degraded / 全 OK→ok / 无记录→unknown）。

当 DQ 状态为 `blocked` 或 `degraded` 时，Agent 应在结论中明确说明质量影响；
分母为零时应回答"不可评估"，不能转换成 0%（如部分工单类型无计划完成时间时，超期率不可评估）。
