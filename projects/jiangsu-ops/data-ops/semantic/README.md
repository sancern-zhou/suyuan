# 江苏运维语义注册中心

`registry.yaml` 是 Agent 解释指标结果的业务语义来源，登记数据集、粒度、适用范围、时间窗口、质量限制和关键指标的分子/分母。

- Cube schema 负责执行查询；
- dbt 和 `sync/datasets/*.yaml` 负责数据实现与字段契约；
- `jiangsu_query_metrics` 从注册中心返回 `semantic_context`，包括指标定义、数据时点和 DQ 状态；
- 修改指标口径后运行 `python validate_registry.py`，并同步更新对应 Cube、dbt 和数据集契约。

当 DQ 状态为 `blocked` 或 `degraded` 时，Agent 应在结论中明确说明质量影响；分母为零时应回答“不可评估”，不能转换成 0%。
