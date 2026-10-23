# 许昌语义注册中心

`registry.yaml` 维护业务口径、数据范围和限制；Cube schema 维护执行定义；Python 工具的
`CATALOG` 维护可查询成员。`catalog.generated.yaml` 是供 AI 编程维护和审查的生成索引，
不是新的业务语义来源。

提交前运行：

```bash
python projects/xuchang/data-ops/semantic/validate_registry.py
python projects/xuchang/data-ops/semantic/gen_semantic_artifacts.py --check
```

乡镇数据必须明确选择 `caliber=app` 或 `caliber=src`；本地累计排名不等于官方统计口径；
字段缺失或数据覆盖不足时，Agent 必须在结论中说明影响。
