# 许昌语义注册中心

`registry.yaml` 维护业务口径、数据范围、限制与成员中文标题；Cube schema 维护执行定义
（可查询成员的唯一真相）。`gen_semantic_artifacts.py` 把两者合成
`backend/app/tools/query/xuchang_cube_metrics/catalog.generated.json`（工具 fail-closed
加载的成员白名单）。改口径只改 schema/registry 后重跑生成器，不再手工维护工具内目录。

提交前运行：

```bash
python projects/xuchang/data-ops/semantic/validate_registry.py
python projects/xuchang/data-ops/semantic/gen_semantic_artifacts.py --check
```

乡镇数据必须明确选择 `caliber=app` 或 `caliber=src`；本地累计排名不等于官方统计口径；
字段缺失或数据覆盖不足时，Agent 必须在结论中说明影响。
