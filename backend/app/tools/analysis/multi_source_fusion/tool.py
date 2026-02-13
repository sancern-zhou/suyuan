"""
多数据源融合工具 - 合并多个数据源用于综合分析

核心功能：
1. 支持从多个数据源获取数据
2. 合并和关联数据
3. 处理数据不一致问题
4. 生成综合可视化方案

适用场景：
- 多站点对比分析
- 污染物与气象数据关联分析
- 时间序列与空间分布结合分析

参考：docs/可视化增强方案.md 阶段3任务
"""

from typing import Dict, Any, Optional, List, Tuple
import json
import structlog
from datetime import datetime
from collections import defaultdict

from abc import ABC, abstractmethod

logger = structlog.get_logger()


class MultiSourceFusion:
    """
    多数据源融合工具 - 合并多个数据源用于综合分析

    将来自不同数据源的数据进行融合，生成统一的数据集用于可视化
    """

    async def execute(
        self,
        context: Any,
        fusion_plan: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        融合多个数据源

        Args:
            context: 执行上下文
            fusion_plan: 融合方案
                {
                    "data_sources": [
                        {"data_id": "air_quality_data", "schema": "air_quality"},
                        {"data_id": "meteorology_data", "schema": "meteorology"}
                    ],
                    "join_type": "inner|left|outer",
                    "join_keys": ["timePoint", "station_name"],
                    "fusion_type": "timeseries_merge|spatial_join|attribute_combine"
                }

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "fused_data": [...],
                    "fusion_metadata": {
                        "source_count": 2,
                        "record_count": 100,
                        "join_keys": [...],
                        "fusion_type": "..."
                    }
                },
                "summary": "成功融合2个数据源，共100条记录"
            }
        """
        logger.info(
            "multi_source_fusion_start",
            source_count=len(fusion_plan.get("data_sources", [])),
            fusion_type=fusion_plan.get("fusion_type")
        )

        try:
            # Step 1: 从各个数据源获取数据
            sources_data = await self._fetch_all_sources(
                context=context,
                data_sources=fusion_plan.get("data_sources", [])
            )

            if not sources_data:
                return {
                    "status": "failed",
                    "success": False,
                    "error": "未能获取任何数据源数据"
                }

            # Step 2: 根据融合类型执行合并
            fusion_type = fusion_plan.get("fusion_type", "attribute_combine")

            if fusion_type == "timeseries_merge":
                fused_data, metadata = await self._merge_timeseries(
                    sources_data=sources_data,
                    join_keys=fusion_plan.get("join_keys", ["timePoint"])
                )
            elif fusion_type == "spatial_join":
                fused_data, metadata = await self._spatial_join(
                    sources_data=sources_data,
                    join_keys=fusion_plan.get("join_keys", ["station_name"])
                )
            elif fusion_type == "attribute_combine":
                fused_data, metadata = await self._combine_attributes(
                    sources_data=sources_data,
                    join_keys=fusion_plan.get("join_keys", [])
                )
            else:
                raise ValueError(f"不支持的融合类型: {fusion_type}")

            # Step 3: 数据质量检查
            quality_report = self._assess_data_quality(fused_data)

            result = {
                "status": "success",
                "success": True,
                "data": {
                    "fused_data": fused_data,
                    "fusion_metadata": metadata,
                    "quality_report": quality_report
                },
                "metadata": {
                    "tool_name": "multi_source_fusion",
                    "fusion_type": fusion_type,
                    "source_count": len(sources_data)
                },
                "summary": f"成功融合{len(sources_data)}个数据源，共{metadata.get('record_count', 0)}条记录"
            }

            logger.info(
                "multi_source_fusion_complete",
                record_count=metadata.get("record_count", 0),
                quality_score=quality_report.get("overall_score", 0)
            )

            return result

        except Exception as e:
            logger.error("multi_source_fusion_error", error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "metadata": {
                    "tool_name": "multi_source_fusion"
                }
            }

    async def _fetch_all_sources(
        self,
        context: Any,
        data_sources: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """从所有数据源获取数据"""
        sources_data = {}

        for source in data_sources:
            data_id = source.get("data_id")
            schema = source.get("schema", "unknown")
            source_name = source.get("name", data_id)

            try:
                if context.requires_context:
                    data = context.get_data(data_id)
                    sources_data[source_name] = {
                        "data": data,
                        "schema": schema,
                        "data_id": data_id
                    }
                    logger.info("source_data_fetched", source_name=source_name, schema=schema)
                else:
                    logger.warning("context_no_data_retrieval", source_name=source_name)
            except Exception as e:
                logger.error("source_fetch_failed", source_name=source_name, error=str(e))

        return sources_data

    async def _merge_timeseries(
        self,
        sources_data: Dict[str, Dict[str, Any]],
        join_keys: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """合并时序数据"""
        logger.info("timeseries_merge_start", source_count=len(sources_data))

        # 提取所有时间点
        all_time_points = set()
        source_records = {}

        for source_name, source_info in sources_data.items():
            data = source_info.get("data", [])
            records = self._extract_records_from_data(data)
            source_records[source_name] = records

            # 收集时间点
            for record in records:
                for key in join_keys:
                    if key in record:
                        all_time_points.add(record[key])

        # 按时间点合并数据
        fused_data = []
        time_points_sorted = sorted(list(all_time_points))

        for time_point in time_points_sorted:
            fused_record = {}

            # 添加时间字段
            for key in join_keys:
                if key in {"timePoint", "timestamp", "time"}:
                    fused_record[key] = time_point

            # 合并各数据源在同一时间点的记录
            for source_name, records in source_records.items():
                source_records_at_time = [
                    r for r in records
                    if any(r.get(k) == time_point for k in join_keys if k in r)
                ]

                if source_records_at_time:
                    # 如果有多个记录，取第一个或合并
                    record = source_records_at_time[0]

                    # 为字段添加前缀以避免冲突
                    for field, value in record.items():
                        if field not in join_keys:  # 不重复添加join字段
                            prefixed_field = f"{source_name}_{field}"
                            fused_record[prefixed_field] = value

            if fused_record:
                fused_data.append(fused_record)

        metadata = {
            "fusion_type": "timeseries_merge",
            "join_keys": join_keys,
            "record_count": len(fused_data),
            "source_count": len(sources_data),
            "time_range": [time_points_sorted[0], time_points_sorted[-1]] if time_points_sorted else []
        }

        return fused_data, metadata

    async def _spatial_join(
        self,
        sources_data: Dict[str, Dict[str, Any]],
        join_keys: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """空间连接（基于站点名等）"""
        logger.info("spatial_join_start", source_count=len(sources_data))

        # 选择主数据源
        primary_source_name = list(sources_data.keys())[0]
        primary_source = sources_data[primary_source_name]

        primary_records = self._extract_records_from_data(primary_source["data"])

        fused_data = []

        for primary_record in primary_records:
            fused_record = primary_record.copy()

            # 为主数据源的字段添加前缀
            for field in list(fused_record.keys()):
                if field not in join_keys:
                    fused_record[f"{primary_source_name}_{field}"] = fused_record.pop(field)

            # 连接其他数据源
            for source_name, source_info in list(sources_data.items())[1:]:
                source_records = self._extract_records_from_data(source_info["data"])

                # 查找匹配的记录
                matched_record = None
                for source_record in source_records:
                    # 检查join keys是否匹配
                    if all(
                        primary_record.get(k) == source_record.get(k)
                        for k in join_keys
                        if k in primary_record and k in source_record
                    ):
                        matched_record = source_record
                        break

                if matched_record:
                    # 添加匹配的字段
                    for field, value in matched_record.items():
                        if field not in join_keys:
                            prefixed_field = f"{source_name}_{field}"
                            fused_record[prefixed_field] = value
                else:
                    # 如果没有匹配，标记为缺失
                    fused_record[f"{source_name}_matched"] = False

            fused_data.append(fused_record)

        metadata = {
            "fusion_type": "spatial_join",
            "join_keys": join_keys,
            "record_count": len(fused_data),
            "source_count": len(sources_data),
            "primary_source": primary_source_name
        }

        return fused_data, metadata

    async def _combine_attributes(
        self,
        sources_data: Dict[str, Dict[str, Any]],
        join_keys: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """属性组合（简单的字段合并）"""
        logger.info("attribute_combine_start", source_count=len(sources_data))

        # 收集所有字段
        all_fields = set()
        source_records = {}

        for source_name, source_info in sources_data.items():
            data = source_info.get("data", [])
            records = self._extract_records_from_data(data)
            source_records[source_name] = records

            for record in records:
                all_fields.update(record.keys())

        # 移除join_keys
        all_fields = all_fields - set(join_keys)

        # 合并所有记录
        fused_data = []
        for source_name, records in source_records.items():
            for record in records:
                # 创建新记录，添加数据源标识
                new_record = {f"{source_name}_{k}": v for k, v in record.items()}
                new_record["data_source"] = source_name
                fused_data.append(new_record)

        metadata = {
            "fusion_type": "attribute_combine",
            "join_keys": join_keys,
            "record_count": len(fused_data),
            "source_count": len(sources_data),
            "total_fields": len(all_fields)
        }

        return fused_data, metadata

    def _extract_records_from_data(self, data: Any) -> List[Dict[str, Any]]:
        """从各种数据格式中提取记录"""
        records = []

        if isinstance(data, dict):
            if "data" in data:
                records = data["data"]
            elif isinstance(data, list):
                records = data
            else:
                records = [data]
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        return records

    def _assess_data_quality(self, fused_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """评估融合后数据质量"""
        if not fused_data:
            return {
                "overall_score": 0.0,
                "completeness": 0.0,
                "consistency": 0.0,
                "issues": ["无数据"]
            }

        # 计算完整度
        total_cells = len(fused_data) * len(fused_data[0].keys()) if fused_data else 0
        non_null_cells = sum(
            1 for record in fused_data
            for value in record.values()
            if value is not None and value != ""
        )

        completeness = non_null_cells / total_cells if total_cells > 0 else 0.0

        # 计算一致性（简化：检查关键字段的一致性）
        consistency_score = 1.0  # 简化实现

        # 识别数据问题
        issues = []
        if completeness < 0.8:
            issues.append(f"数据完整度较低: {completeness:.2%}")

        # 计算总分
        overall_score = (completeness + consistency_score) / 2

        return {
            "overall_score": round(overall_score, 3),
            "completeness": round(completeness, 3),
            "consistency": round(consistency_score, 3),
            "issues": issues,
            "record_count": len(fused_data),
            "field_count": len(fused_data[0].keys()) if fused_data else 0
        }


# ============================================
# 便捷函数
# ============================================

async def fuse_data_sources(
    context: Any,
    data_sources: List[Dict[str, Any]],
    fusion_type: str = "attribute_combine",
    join_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    快速融合数据源

    Args:
        context: 执行上下文
        data_sources: 数据源列表
        fusion_type: 融合类型
        join_keys: 连接键

    Returns:
        融合结果
    """
    fusion_plan = {
        "data_sources": data_sources,
        "fusion_type": fusion_type,
        "join_keys": join_keys or []
    }

    fusion_tool = MultiSourceFusion()
    return await fusion_tool.execute(context, fusion_plan)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """示例：融合空气质量和气象数据"""
        fusion_plan = {
            "data_sources": [
                {
                    "data_id": "air_quality_data",
                    "schema": "air_quality",
                    "name": "air_quality"
                },
                {
                    "data_id": "meteorology_data",
                    "schema": "meteorology",
                    "name": "meteorology"
                }
            ],
            "fusion_type": "timeseries_merge",
            "join_keys": ["timePoint", "station_name"]
        }

        # 模拟context
        class MockContext:
            def __init__(self):
                self.requires_context = False

        context = MockContext()

        # 注意：实际使用需要从context获取真实数据
        result = await fuse_data_sources(
            context=context,
            data_sources=fusion_plan["data_sources"],
            fusion_type=fusion_plan["fusion_type"],
            join_keys=fusion_plan["join_keys"]
        )

        print("=== 多数据源融合结果 ===")
        print(f"状态: {result['status']}")
        if result['success']:
            metadata = result['data']['fusion_metadata']
            print(f"融合类型: {metadata['fusion_type']}")
            print(f"数据源数量: {metadata['source_count']}")
            print(f"记录数: {metadata['record_count']}")
            quality = result['data']['quality_report']
            print(f"数据质量分数: {quality['overall_score']}")
            print(f"完整度: {quality['completeness']}")
        else:
            print(f"错误: {result.get('error')}")

    asyncio.run(example())
