"""
Data Context Manager - Type-Safe Data Storage and Retrieval

This manager provides a unified interface for storing and retrieving validated data
across tool invocations in an agent session. It builds upon the existing HybridMemoryManager
while adding:
- Type-safe data serialization with Pydantic models
- Schema validation and compatibility checking
- Quality report persistence
- Data reference management via TypedDataHandle

Architecture:
- Integrates with existing SessionMemory and DataRegistry
- Maintains in-memory handle cache for fast metadata access
- Automatically externalizes large datasets
- Supports typed deserialization for downstream tools
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union
from uuid import uuid4

import structlog
from pydantic import BaseModel

from app.agent.context.typed_data_handle import TypedDataHandle
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.schemas.common import DataQualityReport, FieldStats
from app.schemas.particulate import ParticulateSample, UnifiedParticulateData
from app.schemas.vocs import VOCsSample, UnifiedVOCsData
from app.schemas.unified import UnifiedDataRecord, ParticulateAnalysisResult  # 新增 ParticulateAnalysisResult
from app.schemas.pmf import PMFResult
from app.schemas.visualization import ChartResponse
from app.schemas.obm import OBMOFPResult
from app.schemas.enhanced_obm import EnhancedOBMResult
from app.schemas.trajectory import TrajectorySourceAnalysisResult
from app.services.data_registry import data_registry
from app.utils.data_standardizer import get_data_standardizer  # UDF v2.0 强制标准化

logger = structlog.get_logger()


# Schema to Pydantic model mapping
SCHEMA_MODEL_MAP: Dict[str, Type[BaseModel]] = {
    "vocs": VOCsSample,
    "vocs_unified": UnifiedVOCsData,
    "particulate": ParticulateSample,
    "particulate_unified": UnifiedParticulateData,  # 统一颗粒物数据格式
    "pmf_result": PMFResult,
    "chart_response": ChartResponse,
    "obm_ofp_result": OBMOFPResult,
    "enhanced_obm_result": EnhancedOBMResult,  # 增强OBM分析结果
    "guangdong_stations": UnifiedDataRecord,  # 广东站点数据
    "air_quality_unified": UnifiedDataRecord,  # 空气质量统一数据
    "air_quality_5min": UnifiedDataRecord,  # 5分钟数据 (get_5min_data)
    "regional_city_comparison": UnifiedDataRecord,  # 城市级区域对比数据
    "regional_station_comparison": UnifiedDataRecord,  # 站点级区域对比数据
    "trajectory_analysis_result": TrajectorySourceAnalysisResult,  # 深度溯源结果
    "particulate_analysis": ParticulateAnalysisResult,  # 颗粒物分析结果 (calculate_soluble/carbon/crustal)
    "meteorology_unified": UnifiedDataRecord,  # 通用气象数据 (get_universal_meteorology)
    "weather": UnifiedDataRecord,  # 历史气象数据 (get_weather_data)
}


class DataContextManager:
    """
    Unified data context manager with type-safe operations.

    This manager acts as the bridge between tools and the underlying memory/storage
    systems, ensuring that:
    - All data is validated before storage
    - Schema information is preserved
    - Quality reports are accessible
    - Type-safe deserialization is automatic

    Example Usage:
        manager = DataContextManager(memory_manager)

        # Save validated data
        handle = manager.save_data(
            data=vocs_samples,  # List[VOCsSample]
            schema="vocs",
            quality_report=report,
            field_stats=stats
        )

        # Load with type safety
        vocs_data = manager.get_data(handle.full_id, expected_schema="vocs")
        # Returns List[VOCsSample]
    """

    def __init__(self, memory_manager: HybridMemoryManager) -> None:
        """
        Initialize data context manager.

        Args:
            memory_manager: Underlying hybrid memory manager
        """
        self.memory = memory_manager
        self.registry = data_registry
        self._handles: Dict[str, TypedDataHandle] = {}

        logger.info(
            "data_context_manager_initialized",
            session_id=memory_manager.session_id
        )

    def save_data(
        self,
        data: Union[List[BaseModel], List[Dict]],  # 支持两种输入格式
        schema: str,
        quality_report: Optional[DataQualityReport] = None,
        field_stats: Optional[List[FieldStats]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save data and return the data ID string.

        优化：不在每条记录中重复添加data_id字段
        - 减少数据冗余和上下文大小
        - data_id在观察结果级别引用即可
        - 避免采样数据展示时的重复

        Args:
            data: List of Pydantic model instances or dictionaries
            schema: Schema identifier (e.g., "vocs", "particulate", "pmf_result")
            quality_report: Data quality validation report
            field_stats: Field-level statistics
            metadata: Additional metadata

        Returns:
            str: Full data ID (format: "schema:v1:hash") for accessing the data
                 TypedDataHandle is cached internally and accessible via get_handle()

        Raises:
            ValueError: If data is empty or types are inconsistent
            TypeError: If data items are not Pydantic models or dicts

        Example:
            # Save Pydantic models - returns string ID directly
            data_id = manager.save_data(
                data=vocs_samples,  # List[VOCsSample]
                schema="vocs",
                quality_report=validation_result.report,
                field_stats=validation_result.field_stats,
                metadata={"question": "深圳市VOCs数据"}
            )
            # data_id = "vocs:v1:abc123def456..." (string)

            # Save dictionary data (UDF v2.0 format)
            data_id = manager.save_data(
                data=result_list,  # List[Dict]
                schema="pmf_result",
                metadata={"tool": "calculate_pmf"}
            )
            # Directly use data_id in tool results
        """
        # 0. 【空列表防护】提前检查数据是否为空
        if not data:
            raise ValueError("Cannot save empty data")

        # 【UDF v2.0强制标准化】在保存前自动标准化数据
        # 1. 确定是否需要标准化
        standardized_data = data
        field_mapping_applied = False

        # 需要强制标准化的schema类型
        STANDARDIZATION_REQUIRED_SCHEMAS = {
            "vocs",  # ✅ 新增：强制标准化原始VOCs数据
            "vocs_unified",
            "air_quality_unified",
            "guangdong_stations",
            "regional_city_comparison",
            "regional_station_comparison",
            "particulate",
            "particulate_unified",  # 统一颗粒物数据格式
            "weather",
            "meteorological_data",
            "meteorology_unified"  # 通用气象数据 (get_universal_meteorology)
        }

        # 检查是否需要强制标准化
        if schema in STANDARDIZATION_REQUIRED_SCHEMAS:
            # 检查metadata是否明确指示已标准化
            if not (metadata and metadata.get("field_mapping_applied")):
                logger.info(
                    "data_standardization_required",
                    schema=schema,
                    record_count=len(data),
                    first_data_keys=list(data[0].keys())[:20] if data and len(data) > 0 else [],
                    reason="schema_in_required_list_and_no_field_mapping_applied_flag"
                )

                # 2. Check data type and convert to dict if needed
                if isinstance(data[0], BaseModel):
                    # Pydantic models - convert to dict for standardization
                    serialized_data = [item.dict() for item in data]
                elif isinstance(data[0], dict):
                    # Already dictionaries - use directly
                    serialized_data = data
                else:
                    raise TypeError(f"Data items must be Pydantic models or dictionaries, got {type(data[0])}")

                # 3. 获取全局数据标准化器并标准化
                try:
                    data_standardizer = get_data_standardizer()
                    standardized_records = data_standardizer.standardize(serialized_data)
                    standardized_data = standardized_records
                    field_mapping_applied = True

                    # 【关键修复】对于 particulate_unified schema，将扁平数据转换为嵌套格式
                    # API 返回的颗粒物数据是扁平结构（离子在顶层），需要聚合到 components 字段
                    if schema == "particulate_unified" and isinstance(standardized_records, list):
                        logger.info(
                            "converting_flat_to_nested_format",
                            schema=schema,
                            record_count=len(standardized_records),
                            reason="API返回数据为扁平结构，需要聚合到components字段"
                        )
                        # 【调试】输出第一条标准化后的记录，检查字段
                        logger.info(
                            "[DEBUG] 标准化后第一条记录",
                            first_record_keys=list(standardized_records[0].keys()) if standardized_records else [],
                            first_record_has_components="components" in standardized_records[0] if standardized_records else False,
                            sample=standardized_records[0] if standardized_records else None
                        )
                        # 【新增调试】检查所有数值型字段（可能是离子）
                        if standardized_records:
                            first_record = standardized_records[0]
                            numeric_fields = {k: v for k, v in first_record.items() if isinstance(v, (int, float)) and k not in ['station_code', 'lat', 'lon']}
                            logger.info(
                                "[DEBUG] 所有数值型字段",
                                numeric_fields=list(numeric_fields.keys()),
                                sample_values={k: numeric_fields[k] for k in list(numeric_fields.keys())[:10]}
                            )
                        nested_records = []
                        for idx, record in enumerate(standardized_records):
                            if isinstance(record, dict):
                                # 【调试】第一条记录检查 components 聚合情况
                                if idx == 0:
                                    logger.info(
                                        "[DEBUG] from_raw_data处理前",
                                        record_keys=list(record.keys())[:15],
                                        has_components_before="components" in record,
                                        has_pm2_5_before="PM2_5" in record
                                    )
                                # 使用 UnifiedParticulateData.from_raw_data() 转换
                                # 注意：schema现在原生支持PM2_5字段（大写），from_raw_data的known_fields已包含PM2_5变体
                                nested_record = UnifiedParticulateData.from_raw_data(record)
                                # 验证 PM2_5 是否正确保留（schema 已原生支持，无需手动处理）
                                if idx == 0:
                                    nested_dump = nested_record.model_dump()
                                    logger.info(
                                        "[DEBUG] from_raw_data处理后",
                                        nested_keys=list(nested_dump.keys()),
                                        nested_components=nested_dump.get("components", {}),
                                        has_PM2_5="PM2_5" in nested_dump,
                                        PM2_5_value=nested_dump.get("PM2_5")
                                    )
                                nested_records.append(nested_record.model_dump())
                            else:
                                nested_records.append(record)
                        standardized_data = nested_records
                        logger.info(
                            "flat_to_nested_conversion_complete",
                            schema=schema,
                            original_count=len(standardized_records),
                            converted_count=len(standardized_data),
                            sample_keys=list(standardized_data[0].keys()) if standardized_data else []
                        )

                    # 【新增】碳组分字段标准化：将 elemental_carbon → EC, organic_carbon → OC
                    # 便于分析工具（calculate_carbon）直接使用简短字段名
                    carbon_field_mapping = {
                        "elemental_carbon": "EC",
                        "organic_carbon": "OC"
                    }
                    for record in standardized_data:
                        if isinstance(record, dict) and "components" in record:
                            components = record["components"]
                            if isinstance(components, dict):
                                for old_key, new_key in carbon_field_mapping.items():
                                    if old_key in components:
                                        components[new_key] = components.pop(old_key)
                                        logger.debug(
                                            "carbon_field_remapped",
                                            old_key=old_key,
                                            new_key=new_key,
                                            value=components.get(new_key)
                                        )

                    # 【关键调试】检查标准化后的第一条记录是否包含species_data
                    if schema == "vocs_unified" and standardized_records:
                        first_record = standardized_records[0] if isinstance(standardized_records, list) else standardized_records
                        has_species_data = "species_data" in first_record if isinstance(first_record, dict) else False
                        # 使用safe处理避免Unicode字符导致的编码错误（Windows GBK问题）
                        if isinstance(first_record, dict):
                            from app.utils.data_standardizer import _safe_for_logging
                            safe_keys = _safe_for_logging(list(first_record.keys())[:10])
                        else:
                            safe_keys = []
                        logger.info(
                            "data_standardization_applied",
                            schema=schema,
                            original_count=len(data),
                            standardized_count=len(standardized_records),
                            first_record_keys=safe_keys,
                            has_species_data=has_species_data,
                            field_mapping_info=data_standardizer.get_field_mapping_info()
                        )
                    else:
                        logger.info(
                            "data_standardization_applied",
                            schema=schema,
                            original_count=len(data),
                            standardized_count=len(standardized_records),
                            field_mapping_info=data_standardizer.get_field_mapping_info()
                        )
                except Exception as exc:
                    logger.warning(
                        "data_standardization_failed",
                        schema=schema,
                        error=str(exc),
                        message="继续保存未标准化的数据"
                    )
                    standardized_data = data
            else:
                logger.info(
                    "data_standardization_skipped",
                    schema=schema,
                    reason="field_mapping_applied_already_set",
                    first_data_keys=list(data[0].keys())[:20] if data and len(data) > 0 else [],
                    has_measurements="measurements" in data[0] if data and len(data) > 0 else False,
                    field_mapping_applied_flag=metadata.get("field_mapping_applied") if metadata else None
                )
        else:
            logger.debug(
                "data_standardization_not_required",
                schema=schema,
                reason="schema_not_in_required_list"
            )

        # 4. 强制设置UDF v2.0标记
        if metadata is None:
            metadata = {}
        if "schema_version" not in metadata:
            metadata["schema_version"] = "v2.0"  # 强制标记为v2.0
            logger.debug(
                "schema_version_forced_to_v2_0",
                schema=schema,
                original_metadata=metadata
            )

        # 5. Record field mapping info if applied
        if field_mapping_applied:
            try:
                data_standardizer = get_data_standardizer()
                metadata["field_mapping_applied"] = True
                metadata["field_mapping_info"] = data_standardizer.get_field_mapping_info()
            except Exception as exc:
                logger.warning(
                    "failed_to_record_field_mapping_info",
                    schema=schema,
                    error=str(exc)
                )

        # 6. Check data type and convert to dict if needed (使用标准化后的数据)
        if isinstance(standardized_data[0], BaseModel):
            # Pydantic models - convert to dict
            model_class = type(standardized_data[0])
            serialized_data = [item.dict() for item in standardized_data]
            is_pydantic = True
        elif isinstance(standardized_data[0], dict):
            # Already dictionaries - use directly
            model_class = dict
            serialized_data = standardized_data
            is_pydantic = False
        else:
            raise TypeError(f"Data items must be Pydantic models or dictionaries, got {type(standardized_data[0])}")

        # 【关键调试】确认保存前的数据包含species_data
        if schema == "vocs_unified" and serialized_data:
            first_record = serialized_data[0]
            has_species_data = "species_data" in first_record if isinstance(first_record, dict) else False
            logger.info(
                "data_before_save",
                schema=schema,
                record_count=len(serialized_data),
                first_record_keys=list(first_record.keys())[:10] if isinstance(first_record, dict) else [],
                has_species_data=has_species_data
            )

        if not all(isinstance(item, (BaseModel, dict)) for item in standardized_data):
            raise TypeError("All items must be Pydantic models or dictionaries")

        # 6.1 【修复】将field_stats从字典列表转换为FieldStats对象列表
        # get_vocs_data.tool传入的是[fs.dict() for fs in result.field_stats]
        # 【关键修复】如果数据经过标准化，需要从species_data/components字段重新提取物种
        normalized_field_stats: List[FieldStats] = []
        if field_stats:
            for fs in field_stats:
                if isinstance(fs, dict):
                    normalized_field_stats.append(FieldStats(**fs))
                elif isinstance(fs, FieldStats):
                    normalized_field_stats.append(fs)
                else:
                    logger.warning(
                        "unexpected_field_stats_type",
                        type=type(fs),
                        message="Skipping invalid field_stats item"
                    )
            field_stats = normalized_field_stats
            logger.debug(
                "field_stats_normalized",
                count=len(field_stats),
                first_field=field_stats[0].name if field_stats else None
            )

        # 6.2 【关键修复】数据标准化后，从species_data/components字段重新提取物种作为field_stats
        # 【修复】查找第一条有实际数据的记录，而非总是用第0条（可能为空）
        if field_mapping_applied and schema in ("vocs_unified", "particulate_unified"):
            if serialized_data and isinstance(serialized_data[0], dict):
                first_record = serialized_data[0]
                if schema == "vocs_unified" and "species_data" in first_record:
                    # 【修复】查找第一条有species数据的记录
                    species_record = None
                    for record in serialized_data:
                        if isinstance(record, dict) and record.get("species_data"):
                            species_record = record
                            break

                    if species_record:
                        species_keys = list(species_record["species_data"].keys())
                        field_stats = [
                            FieldStats(name=species, minimum=0, maximum=0, mean=0, missing=0, total=len(serialized_data))
                            for species in species_keys
                        ]
                        logger.info(
                            "field_stats_rebuilt_from_species_data",
                            species_count=len(species_keys),
                            species_names=species_keys[:5],
                            found_at_record=serialized_data.index(species_record)
                        )
                    else:
                        logger.warning(
                            "no_valid_species_data_found",
                            total_records=len(serialized_data),
                            message="所有记录的species_data都为空，保留原有field_stats"
                        )
                elif schema == "particulate_unified" and "components" in first_record:
                    # 【修复】查找第一条有components数据的记录
                    component_record = None
                    for record in serialized_data:
                        if isinstance(record, dict) and record.get("components"):
                            component_record = record
                            break

                    if component_record:
                        component_keys = list(component_record["components"].keys())
                        field_stats = [
                            FieldStats(name=comp, minimum=0, maximum=0, mean=0, missing=0, total=len(serialized_data))
                            for comp in component_keys
                        ]
                        logger.info(
                            "field_stats_rebuilt_from_components",
                            component_count=len(component_keys),
                            component_names=component_keys[:5],
                            found_at_record=serialized_data.index(component_record)
                        )
                    else:
                        logger.warning(
                            "no_valid_components_found",
                            total_records=len(serialized_data),
                            message="所有记录的components都为空，保留原有field_stats"
                        )

        # 7. Generate data ID
        data_id = uuid4().hex
        full_id = f"{schema}:v1:{data_id}"

        # 8. 【优化】直接保存序列化数据，不在每条记录中添加data_id字段
        # 避免重复冗余，减少上下文大小
        # 使用safe处理避免Unicode字符导致的编码错误（Windows GBK问题）
        sample_keys = []
        if serialized_data:
            from app.utils.data_standardizer import _safe_for_logging
            raw_keys = list(serialized_data[0].keys())[:5]
            sample_keys = _safe_for_logging(raw_keys)

        logger.debug(
            "saving_data_without_item_data_id",
            full_id=full_id,
            schema=schema,
            record_count=len(serialized_data),
            sample_keys=sample_keys
        )

        # 9. Save to session memory with quality info
        # 【关键修复】使用标准化后的数据 standardized_data，而非原始的 serialized_data
        path = self.memory.session.save_data_to_file(
            data=standardized_data,
            data_id=full_id,
            registry_schema=schema,
            registry_metadata=metadata or {},
            quality_report=quality_report,
            field_stats=field_stats
        )

        # 10. Create typed handle
        # For dict data, try to get model class from SCHEMA_MODEL_MAP
        if is_pydantic:
            handle_model_class = model_class
        else:
            # ✅ 修复：从SCHEMA_MODEL_MAP获取model_class，即使输入是字典
            handle_model_class = SCHEMA_MODEL_MAP.get(schema)
            if handle_model_class:
                logger.debug(
                    "using_model_class_from_schema_map",
                    schema=schema,
                    model_class=handle_model_class.__name__
                )

        handle = TypedDataHandle(
            data_id=data_id,
            schema=schema,
            version="v1",
            record_count=len(standardized_data),  # 使用标准化后的数据计数
            model_class=handle_model_class,
            quality_report=quality_report or self._create_default_report(schema, len(standardized_data)),
            field_stats=field_stats or [],
            metadata=metadata
        )

        # 11. Cache handle
        self._handles[full_id] = handle

        logger.info(
            "data_saved_with_id",
            full_id=full_id,
            schema=schema,
            record_count=len(standardized_data),
            data_type="pydantic" if is_pydantic else "dict",
            path=path,
            field_mapping_applied=field_mapping_applied  # 记录是否应用了标准化
        )

        # ✅ 返回字典包含 data_id 和 file_path
        # 计算绝对路径（供 Agent 使用）
        try:
            # path 可能是字符串或 Path 对象，统一转换为 Path
            if isinstance(path, str):
                path_obj = Path(path)
            else:
                path_obj = path

            if path_obj.is_absolute():
                # 已经是绝对路径
                file_path = str(path_obj)
            else:
                # 相对路径，转换为绝对路径
                file_path = str(Path.cwd().parent / path_obj)

            # 统一路径分隔符为 /（适用于 Windows 和 Linux）
            file_path = file_path.replace("\\", "/")
        except Exception as e:
            logger.warning("failed_to_calculate_file_path", path=str(path), error=str(e))
            # 回退到原始路径
            file_path = str(path)

        return {
            "data_id": full_id,
            "file_path": file_path
        }

    def get_data(
        self,
        data_id: str,
        expected_schema: Optional[str] = None
    ) -> List[BaseModel]:
        """
        Load data and automatically deserialize to Pydantic models.

        Args:
            data_id: Full data identifier (e.g., "vocs:v1:abc123")
            expected_schema: Expected schema for validation (optional)

        Returns:
            List of Pydantic model instances

        Raises:
            KeyError: Data ID not found
            ValueError: Schema mismatch

        Example:
            vocs_data = manager.get_data("vocs:v1:abc123", expected_schema="vocs")
            # Returns List[VOCsSample]
        """
        # 1. Get handle
        handle = self.get_handle(data_id)

        # 2. Schema validation
        if expected_schema and not handle.is_compatible_with(expected_schema):
            raise ValueError(
                f"Schema mismatch: expected '{expected_schema}', "
                f"got '{handle.schema}'"
            )

        # 3. Load raw data
        raw_data = self._load_raw_data(data_id)

        # 4. Deserialize to Pydantic objects
        model_class = handle.model_class

        # Check if model_class is None (schema not in SCHEMA_MODEL_MAP)
        if model_class is None:
            logger.warning(
                "model_class_is_none_returning_raw_data",
                data_id=data_id,
                schema=handle.schema,
                message=f"Schema '{handle.schema}' not in SCHEMA_MODEL_MAP, returning raw data as dicts"
            )
            # Return raw data as-is if no model class is available
            # This happens when schema is not in SCHEMA_MODEL_MAP
            # Convert to a list of plain dicts if needed
            if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
                return raw_data
            else:
                raise TypeError(
                    f"Cannot deserialize data for schema '{handle.schema}': "
                    f"No model class available and raw data is not a list of dicts"
                )

        try:
            # Schema的model_validator会自动处理字段转换
            typed_data = [model_class(**item) for item in raw_data]
        except Exception as exc:
            logger.error(
                "deserialization_failed",
                data_id=data_id,
                model_class=model_class.__name__ if model_class else "Unknown",
                error=str(exc)
            )
            # 【修复】降级返回原始数据，避免反序列化失败导致工具调用完全失败
            logger.warning(
                "deserialization_failed_fallback_to_raw",
                data_id=data_id,
                reason="反序列化失败，降级返回原始字典数据",
                record_count=len(raw_data)
            )
            # 返回原始数据（字典列表）
            if isinstance(raw_data, list):
                return raw_data
            else:
                return [raw_data]

        logger.info(
            "data_loaded_and_typed",
            data_id=data_id,
            schema=handle.schema,
            record_count=len(typed_data)
        )

        return typed_data

    def get_raw_data(self, data_id: str) -> List[Dict[str, Any]]:
        """
        Load raw data without deserializing to Pydantic models.

        This method returns data in its original dictionary format, which is useful
        for analysis results (PMF, OBM) that are already in standard dictionary format.

        Args:
            data_id: Full data identifier

        Returns:
            List of dictionaries (raw data)

        Raises:
            KeyError: Data ID not found

        Example:
            # Get PMF result as raw dictionary
            pmf_result = manager.get_raw_data("pmf_result:v1:abc123")
            # Returns [{'sources': [...], 'timeseries': [...], ...}]
        """
        logger.info(
            "loading_raw_data",
            data_id=data_id
        )
        raw_data = self._load_raw_data(data_id)

        logger.info(
            "raw_data_loaded",
            data_id=data_id,
            record_count=len(raw_data),
            data_type="dict" if raw_data and isinstance(raw_data[0], dict) else type(raw_data[0]).__name__
        )

        return raw_data

    def get_handle(self, data_id: str) -> TypedDataHandle:
        """
        Get data handle without loading full data.

        方案A优化：只支持长格式ID (schema:v1:hash)
        - 移除了短格式ID (data_N) 的支持
        - 简化解析逻辑，提高性能
        - 统一ID格式，避免混淆

        Args:
            data_id: Full data identifier (format: schema:v1:hash)

        Returns:
            TypedDataHandle with metadata

        Raises:
            KeyError: Data ID not found
            ValueError: Invalid data_id format (must be long format)
        """
        # Check cache first
        if data_id in self._handles:
            return self._handles[data_id]

        # Try to reconstruct from session memory
        raw_data = self._load_raw_data(data_id)
        if not raw_data:
            raise KeyError(f"Data not found: {data_id}")

        # Parse data_id - 只支持长格式
        parts = data_id.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid data_id format: {data_id}. "
                f"Expected format: 'schema:v1:hash' (long format)"
            )

        schema, version, short_id = parts

        logger.info(
            "data_id_parsed",
            data_id=data_id,
            schema=schema,
            version=version
        )

        # Get model class
        model_class = SCHEMA_MODEL_MAP.get(schema)
        if not model_class:
            logger.warning(
                "unknown_schema_for_data_id",
                data_id=data_id,
                schema=schema,
                message="Using dict type for unknown schema"
            )
            model_class = None

        # Get registry ID to fetch quality info and metadata
        registry_id = self.memory.session.get_registry_id(data_id)

        quality_report = None
        field_stats = []
        metadata = None

        if registry_id:
            try:
                entry = self.registry.get_metadata(registry_id)
                if entry:
                    quality_report = entry.quality_report
                    # Convert field_stats from List[Dict] to List[FieldStats] objects
                    field_stats = [FieldStats(**stat_dict) for stat_dict in entry.field_stats] if entry.field_stats else []
                    # Load metadata for pollutant inference in smart_chart_generator
                    metadata = entry.metadata if hasattr(entry, 'metadata') else None
                    logger.info(
                        "registry_metadata_loaded",
                        data_id=data_id,
                        has_metadata=metadata is not None,
                        metadata_keys=list(metadata.keys()) if metadata else []
                    )
            except Exception as exc:
                logger.warning(
                    "failed_to_load_registry_metadata",
                    data_id=data_id,
                    error=str(exc)
                )

        # Create handle - 【修复】传递metadata以支持smart_chart_generator的污染物推断
        handle = TypedDataHandle(
            data_id=short_id,
            schema=schema,
            version=version,
            record_count=len(raw_data) if isinstance(raw_data, list) else 1,
            model_class=model_class,
            quality_report=quality_report or self._create_default_report(schema, len(raw_data) if isinstance(raw_data, list) else 1),
            field_stats=field_stats,
            metadata=metadata
        )

        # Cache for next access
        self._handles[data_id] = handle

        logger.info(
            "data_handle_created_and_cached",
            data_id=data_id,
            schema=schema,
            cached=True
        )

        return handle

    def exists(self, data_id: str) -> bool:
        """Check if data ID exists."""
        if data_id in self._handles:
            return True
        try:
            raw_data = self._load_raw_data(data_id)
            return raw_data is not None
        except Exception:
            return False

    def list_data(self, schema: Optional[str] = None) -> List[str]:
        """
        List all available data IDs in current session.

        Args:
            schema: Optional schema filter

        Returns:
            List of full data IDs
        """
        all_ids = list(self._handles.keys())

        # Also check session memory for non-cached data
        for data_id in self.memory.session.data_files.keys():
            if data_id not in all_ids:
                all_ids.append(data_id)

        # Filter by schema if specified
        if schema:
            all_ids = [
                data_id for data_id in all_ids
                if data_id.startswith(f"{schema}:")
            ]

        return sorted(all_ids)

    def _load_raw_data(self, data_id: str) -> List[Dict[str, Any]]:
        """Load raw data from session memory."""
        raw_data = self.memory.session.load_data_from_file(data_id)

        if raw_data is None:
            raise KeyError(f"Data not found in session: {data_id}")

        # 智能适配不同工具的保存格式
        if not isinstance(raw_data, list):
            # 如果是字典，尝试提取数据列表（兼容旧格式）
            if isinstance(raw_data, dict):
                # 提取analysis结果（PMF/OBM返回的完整字典）
                # 【修复】检查嵌套结构：双模式PMF结果中sources在nnls_result里面
                if "sources" in raw_data:
                    # 顶层有sources（单模式结果）
                    logger.info(
                        "extracting_analysis_result_top_level",
                        data_id=data_id,
                        available_keys=list(raw_data.keys())[:5]
                    )
                    return [raw_data]
                elif "nnls_result" in raw_data and isinstance(raw_data["nnls_result"], dict):
                    # 双模式PMF结果：sources在nnls_result里面
                    nnls_result = raw_data["nnls_result"].copy()  # 复制避免修改原始数据
                    if "sources" in nnls_result:
                        logger.info(
                            "extracting_nnls_result_for_dual_mode",
                            data_id=data_id,
                            sources_count=len(nnls_result.get("sources", []))
                        )
                        # 【修复】确保station_name被保留（从顶层合并到nnls_result）
                        if "station_name" not in nnls_result and "station_name" in raw_data:
                            nnls_result["station_name"] = raw_data["station_name"]
                            logger.info(
                                "preserving_station_name_for_visualization",
                                data_id=data_id,
                                station_name=raw_data["station_name"]
                            )
                        # 提取nnls_result用于可视化，保留完整的raw_data用于其他用途
                        return [nnls_result]

                if any(key in raw_data for key in ["timeseries", "species_ofp", "category_summary"]):
                    logger.info(
                        "extracting_analysis_result",
                        data_id=data_id,
                        available_keys=list(raw_data.keys())[:5]
                    )
                    return [raw_data]  # 包装为列表

                # 尝试从data字段提取
                if "data" in raw_data and isinstance(raw_data["data"], list):
                    logger.info(
                        "extracting_data_from_dict",
                        data_id=data_id,
                        source_field="data"
                    )
                    return raw_data["data"]

            raise TypeError(f"Expected list, got {type(raw_data)}")

        return raw_data

    def _create_default_report(
        self,
        schema: str,
        record_count: int
    ) -> DataQualityReport:
        """Create a default quality report when none is provided."""
        return DataQualityReport(
            schema_type=schema,  # 修复字段名
            total_records=record_count,
            valid_records=record_count,
            issues=[],
            missing_rate=0.0,
            summary="No validation report available"
        )

    def clear_cache(self) -> None:
        """Clear handle cache (useful for testing)."""
        self._handles.clear()
        logger.debug(
            "data_context_manager_cache_cleared",
            handles_count=len(self._handles)
        )

    def __repr__(self) -> str:
        return (
            f"<DataContextManager session={self.memory.session_id} "
            f"handles={len(self._handles)}>"
        )
