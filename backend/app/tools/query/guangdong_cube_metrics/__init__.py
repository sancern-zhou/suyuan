"""广东运维指标语义层查询工具（guangdong 分支专属）。

对齐江苏 jiangsu_cube_metrics 模式（2026-10-24 data-ops 化）：指标口径唯一
定义在语义层（projects/guangdong/data-ops/cube/schema/*.js），业务口径登记在
projects/guangdong/data-ops/semantic/registry.yaml，查询结果必须携带
semantic_context（指标定义、粒度、适用范围、数据时点、质量状态和限制）。
"""
