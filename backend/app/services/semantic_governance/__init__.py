# -*- coding: utf-8 -*-
"""语义治理共享库（main 层，项目无关）。

把指标语义层查询工具（Cube REST 模式）里与项目无关的治理中间件收敛到这里，
项目工具（guangdong_cube_metrics / jiangsu_cube_metrics / 后续项目）只保留
项目专属的口径文案、部署参数装配与 execute 编排。参照 graph_seed_service
的全参数签名范式：项目差异全部由调用方以参数传入，本包不含任何项目名、
路径或 schema 硬编码。

模块划分：
  - quality_policy     DQ 状态 → Agent 决策边界文案（纯函数）
  - catalog_store      生成目录产物加载（fail-closed：缺失/损坏拒绝启动）
  - registry           业务语义注册中心加载（fail-open）与元数据组装
  - contract           运行时结果契约校验（profile 规则声明在契约 YAML 里）
  - cube_client        Cube REST 客户端原语：JWT、查询组装、截断、HTTP 调用
  - gating             DQ 质量门查询与新鲜度探针（schema/表/DSN 参数化）
  - audit              best-effort 查询审计写入（列形状由调用方定义）
  - semantic_context   semantic_context 规范形状组装器
"""
from .quality_policy import QUALITY_POLICY, quality_guidance
from .catalog_store import (
    CatalogUnavailable,
    cube_entry,
    cube_names,
    has_member,
    load_catalog,
)
from .registry import cube_metadata, dataset_metadata, load_registry
from .contract import load_contract, validate_result
from .cube_client import (
    build_query,
    flatten_rows,
    make_token,
    query_cube,
    truncate_rows,
)
from .gating import aggregate_quality, data_as_of, quality_status
from .audit import build_insert, write_audit
from .semantic_context import build_semantic_context

__all__ = [
    "QUALITY_POLICY",
    "quality_guidance",
    "CatalogUnavailable",
    "load_catalog",
    "cube_names",
    "cube_entry",
    "has_member",
    "load_registry",
    "cube_metadata",
    "dataset_metadata",
    "load_contract",
    "validate_result",
    "make_token",
    "build_query",
    "flatten_rows",
    "truncate_rows",
    "query_cube",
    "aggregate_quality",
    "quality_status",
    "data_as_of",
    "build_insert",
    "write_audit",
    "build_semantic_context",
]
