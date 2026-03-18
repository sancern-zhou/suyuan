#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版数据格式转换器 (Simplified Data Format Converter)

统一数据层格式，只保留必要的转换逻辑
- API统一返回扁平格式 (flat_direct)
- 字段名统一为PascalCase (Code, StationName, TimePoint)
- 直接转换为UnifiedVOCsData模型

作者: Claude Code
版本: 2.0.0 (简化版)
"""

import structlog
from typing import Dict, List, Any, Tuple, Union, Optional
from datetime import datetime

from app.schemas.vocs import UnifiedVOCsData
from app.schemas.unified_pmf import UnifiedPMFData
from app.schemas.unified_obm import UnifiedOBMOFPData

logger = structlog.get_logger()


# 元数据字段 (不是物种数据)
METADATA_FIELDS = {
    "Code", "StationName", "TimePoint",
    "DataType", "TimeType", "unit", "qcFlag", "metadata", "Quality",
    "remark", "Remark", "note", "Note", "id", "ID"
}


def _extract_vocs_data_list(response: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    从嵌套的API响应中提取VOCs数据列表

    支持的嵌套结构：
    1. {"data": {"result": {"dataList": [...]}}}
    2. {"data": {"results": [{"data": {"result": {"dataList": [...]}}}]}}

    Args:
        response: API响应字典

    Returns:
        数据列表，如果未找到则返回None
    """
    if not isinstance(response, dict):
        return None

    # 结构1: {"data": {"result": {"dataList": [...]}}}
    if "data" in response and isinstance(response["data"], dict):
        data_section = response["data"]

        # 直接在data下找result
        if "result" in data_section and isinstance(data_section["result"], dict):
            result = data_section["result"]
            if "dataList" in result and isinstance(result["dataList"], list):
                logger.debug("Extracted dataList from data.result structure")
                return result["dataList"]

        # 在data下找results列表
        if "results" in data_section and isinstance(data_section["results"], list):
            logger.debug("Found results list, extracting from first result")
            results = data_section["results"]
            if results and isinstance(results[0], dict):
                first_result = results[0]
                if "data" in first_result and isinstance(first_result["data"], dict):
                    nested_data = first_result["data"]
                    if "result" in nested_data and isinstance(nested_data["result"], dict):
                        nested_result = nested_data["result"]
                        if "dataList" in nested_result and isinstance(nested_result["dataList"], list):
                            logger.debug("Extracted dataList from data.results[0].data.result structure")
                            return nested_result["dataList"]

    logger.debug("No recognized nested structure found in response")
    return None


def convert_vocs_data_to_standard(data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Tuple[List[UnifiedVOCsData], str]:
    """
    将API返回的VOCs数据转换为UnifiedVOCsData标准格式

    支持两种输入格式：
    1. 扁平格式 (Flat Direct):
       [
         {
             "Code": "1011b",
             "StationName": "深圳南山",
             "TimePoint": "2025-11-05 00:00:00",
             "乙烯": "3.92",
             "丙烯": "0.43",
             ...
         }
       ]

    2. 嵌套API响应格式 (Nested API Response):
       {
         "data": {
           "result": {
             "dataList": [
               {"Code": "1011b", "StationName": "深圳南山", "TimePoint": "...", "乙烯": "3.92", ...},
               ...
             ]
           }
         }
       }

    输出格式 (UnifiedVOCsData):
        UnifiedVOCsData(
            station_code="1011b",
            station_name="深圳南山",
            timestamp="2025-11-05 00:00:00",
            unit="ppb",
            species_data={"乙烯": 3.92, "丙烯": 0.43, ...}
        )

    Args:
        data: API返回的原始VOCs数据（扁平列表或嵌套响应）

    Returns:
        (converted_data, original_format)
        - converted_data: UnifiedVOCsData模型实例列表
        - original_format: 原始格式标识 ("nested_api" 或 "flat_direct")
    """

    if not data:
        logger.warning("Empty or invalid data provided")
        return [], "empty"

    # 检测输入格式并提取扁平数据
    if isinstance(data, dict):
        # 可能是嵌套API响应格式
        logger.debug("Detected dict input, checking for nested structure")

        # 尝试从嵌套结构提取dataList
        extracted_data = _extract_vocs_data_list(data)

        if extracted_data:
            logger.info(f"Extracted {len(extracted_data)} records from nested API response")
            data = extracted_data
            original_format = "nested_api"
        else:
            # 单个记录不是列表，转换为列表
            logger.debug("Converting single dict record to list")
            data = [data]
            original_format = "flat_direct"
    elif isinstance(data, list):
        # 已经是扁平格式列表
        original_format = "flat_direct"
        logger.info(f"Converting {len(data)} records from flat format")
    else:
        logger.error(f"Unsupported data type: {type(data).__name__}")
        return [], "invalid"

    if not isinstance(data, list):
        logger.warning("Data is not a list after extraction")
        return [], "empty"

    if len(data) == 0:
        logger.warning("Empty data list after extraction")
        return [], original_format

    result = []
    empty_species_count = 0

    for i, record in enumerate(data):
        if not isinstance(record, dict):
            logger.warning(f"Record {i} is not dict, skipping")
            continue

        # 提取元数据字段
        station_code = record.get("Code", "")
        station_name = record.get("StationName", "")
        timestamp = record.get("TimePoint", "")

        # 标准化时间格式 (ISO8601 -> YYYY-MM-DD HH:MM:SS)
        if timestamp and "T" in timestamp:
            timestamp = timestamp.replace("T", " ")

        # 提取物种数据 (排除元数据字段)
        species_data = {}
        for field, value in record.items():
            if field in METADATA_FIELDS:
                continue

            # 只保留数值类型的字段
            try:
                if isinstance(value, (int, float)):
                    species_data[field] = float(value)
                elif isinstance(value, str):
                    # 尝试转换字符串为数值
                    numeric_value = float(value)
                    species_data[field] = numeric_value
            except (ValueError, TypeError):
                # 跳过无法转换的字段 (如"未检出")
                pass

        # 检查是否有物种数据
        if not species_data:
            empty_species_count += 1
            logger.debug(f"Record {i} has no species data: Code={station_code}, TimePoint={timestamp}")

        # 创建UnifiedVOCsData模型实例
        unified_record = UnifiedVOCsData(
            station_code=station_code,
            station_name=station_name,
            timestamp=timestamp,
            unit=record.get("unit", "ppb"),
            species_data=species_data,
            qc_flag=record.get("qcFlag"),
            metadata=record.get("metadata", {})
        )

        result.append(unified_record)

    # 记录转换统计
    logger.info(
        f"Conversion complete: {len(result)} records from {original_format} format, "
        f"{empty_species_count} with empty species_data"
    )

    if empty_species_count > 0:
        logger.warning(
            f"{empty_species_count}/{len(result)} records have no valid species data"
        )

    return result, original_format


def validate_vocs_data_format(data: List[UnifiedVOCsData]) -> Tuple[bool, List[str]]:
    """
    验证UnifiedVOCsData格式数据

    Args:
        data: UnifiedVOCsData模型实例列表

    Returns:
        (is_valid, error_messages)
    """
    if not data:
        return True, []

    errors = []

    for i, record in enumerate(data):
        # 检查必要字段
        if not record.station_code:
            errors.append(f"Record {i}: Missing station_code")

        if not record.timestamp:
            errors.append(f"Record {i}: Missing timestamp")

        # 检查species_data
        if not isinstance(record.species_data, dict):
            errors.append(f"Record {i}: species_data must be a dict")

        if not record.species_data:
            logger.debug(f"Record {i}: species_data is empty (might be normal)")

    is_valid = len(errors) == 0
    return is_valid, errors


# 便捷函数别名 (保持向后兼容)
convert_to_standard = convert_vocs_data_to_standard
validate_format = validate_vocs_data_format


def convert_pmf_result_to_unified(
    data: Union[List[Dict[str, Any]], Dict[str, Any], Any]
) -> Tuple[List[UnifiedPMFData], str]:
    """
    将PMF分析结果转换为UnifiedPMFData标准格式

    支持多种输入格式：
    1. PMFResult对象 (来自calculate_pmf工具)
    2. 字典格式 (包含sources列表)
    3. 列表格式 ([PMFResult] - 来自save_data的返回格式)

    输入格式 (PMFResult):
        {
            "pollutant": "PM2.5",
            "station_name": "深圳南山",
            "sources": [
                {"source_name": "机动车尾气", "contribution_pct": 35.2, "concentration": 12.5},
                ...
            ],
            "timeseries": [...],
            "performance": {"R2": 0.85}
        }

    输出格式 (UnifiedPMFData):
        UnifiedPMFData(
            station_code="",
            station_name="深圳南山",
            pollutant="PM2.5",
            sources=[...],
            timeseries=[...],
            performance={...}
        )

    Args:
        data: PMF分析结果

    Returns:
        (converted_data, original_format)
        - converted_data: UnifiedPMFData模型实例列表
        - original_format: 原始格式标识 ("pmf_result")
    """
    if not data:
        logger.warning("Empty PMF data provided")
        return [], "empty"

    # 如果是列表格式（来自save_data），提取第一个元素
    if isinstance(data, list):
        logger.info("pmf_conversion_detected_list_format")
        if not data:
            logger.warning("pmf_conversion_empty_list")
            return [], "empty"
        data = data[0]
        logger.info(
            "pmf_conversion_extracted_first_item",
            item_type=type(data).__name__
        )

    # 如果不是字典格式，尝试转换
    if not isinstance(data, dict):
        logger.error("pmf_conversion_invalid_input_type", input_type=type(data).__name__)
        return [], "invalid"

    try:
        logger.info(
            "pmf_conversion_start",
            pollutant=data.get("pollutant", "unknown"),
            station_name=data.get("station_name", "unknown"),
            source_count=len(data.get("sources", []))
        )

        # 提取核心数据
        station_name = data.get("station_name", "")
        pollutant = data.get("pollutant", "Unknown")

        # 处理sources - 确保是列表格式
        sources = data.get("sources", [])
        if not isinstance(sources, list):
            logger.warning("pmf_conversion_sources_not_list", sources_type=type(sources).__name__)
            sources = []

        # 转换sources为UnifiedPMFSource格式
        unified_sources = []
        for source in sources:
            if isinstance(source, dict):
                unified_source = {
                    "source_name": source.get("source_name", source.get("source", "Unknown")),
                    "contribution_pct": float(source.get("contribution_pct", source.get("contribution", 0.0))),
                    "concentration": float(source.get("concentration", source.get("conc", 0.0))),
                    "confidence": source.get("confidence", source.get("level", "Unknown"))
                }
                unified_sources.append(unified_source)
            else:
                logger.warning("pmf_conversion_skip_invalid_source", source=source)

        # 处理timeseries - 确保是列表格式
        timeseries = data.get("timeseries", [])
        if not isinstance(timeseries, list):
            logger.warning("pmf_conversion_timeseries_not_list", timeseries_type=type(timeseries).__name__)
            timeseries = []

        # 转换timeseries为UnifiedPMFTimePoint格式
        unified_timeseries = []
        for ts in timeseries:
            if isinstance(ts, dict):
                time_val = ts.get("time", "")
                source_values = ts.get("source_values", ts.get("sources", {}))

                # 确保source_values是字典
                if not isinstance(source_values, dict):
                    logger.warning("pmf_conversion_invalid_source_values", source_values_type=type(source_values).__name__)
                    source_values = {}

                unified_timeseries.append({
                    "time": str(time_val),
                    "source_values": {str(k): float(v) for k, v in source_values.items()}
                })
            else:
                logger.warning("pmf_conversion_skip_invalid_timeseries", ts=ts)

        # 处理performance - 确保是字典格式
        performance = data.get("performance", {})
        if not isinstance(performance, dict):
            logger.warning("pmf_conversion_performance_not_dict", performance_type=type(performance).__name__)
            performance = {}

        # 构建UnifiedPMFData模型
        unified_result = UnifiedPMFData(
            station_code=data.get("station_code", ""),
            station_name=station_name,
            pollutant=pollutant,
            sources=unified_sources,
            timeseries=unified_timeseries,
            performance=performance,
            quality_report=data.get("quality_report"),
            metadata=data.get("metadata", {})
        )

        logger.info(
            "pmf_conversion_complete",
            station_name=station_name,
            pollutant=pollutant,
            source_count=len(unified_sources),
            timeseries_count=len(unified_timeseries)
        )

        return [unified_result], "pmf_result"

    except Exception as e:
        logger.error(
            "pmf_conversion_failed",
            error=str(e),
            exc_info=True
        )
        return [], "error"


def convert_obm_ofp_result_to_unified(
    data: Union[List[Dict[str, Any]], Dict[str, Any], Any]
) -> Tuple[List[UnifiedOBMOFPData], str]:
    """
    将OBM/OFP分析结果转换为UnifiedOBMOFPData标准格式

    支持多种输入格式：
    1. OBMOFPResult对象 (来自calculate_obm_full_chemistry工具)
    2. 字典格式
    3. 列表格式 ([OBMOFPResult] - 来自save_data的返回格式)

    输入格式 (OBMOFPResult):
        {
            "station_name": "深圳南山",
            "species_ofp": [
                {"species": "乙烯", "concentration": 10.5, "ofp": 15.2, "category": "烯烃"},
                ...
            ],
            "category_summary": [...],
            "sensitivity": {...},
            "total_ofp": 129.5
        }

    输出格式 (UnifiedOBMOFPData):
        UnifiedOBMOFPData(
            station_code="",
            station_name="深圳南山",
            species_ofp=[...],
            category_summary=[...],
            sensitivity={...},
            total_ofp=129.5
        )

    Args:
        data: OBM/OFP分析结果

    Returns:
        (converted_data, original_format)
        - converted_data: UnifiedOBMOFPData模型实例列表
        - original_format: 原始格式标识 ("obm_ofp_result")
    """
    if not data:
        logger.warning("Empty OBM data provided")
        return [], "empty"

    # 如果是列表格式（来自save_data），提取第一个元素
    if isinstance(data, list):
        logger.info("obm_conversion_detected_list_format")
        if not data:
            logger.warning("obm_conversion_empty_list")
            return [], "empty"
        data = data[0]
        logger.info(
            "obm_conversion_extracted_first_item",
            item_type=type(data).__name__
        )

    # 如果不是字典格式，尝试转换
    if not isinstance(data, dict):
        logger.error("obm_conversion_invalid_input_type", input_type=type(data).__name__)
        return [], "invalid"

    try:
        logger.info(
            "obm_conversion_start",
            station_name=data.get("station_name", "unknown"),
            total_ofp=data.get("total_ofp", 0),
            species_count=len(data.get("species_ofp", []))
        )

        # 提取核心数据
        station_name = data.get("station_name", "")

        # 处理species_ofp - 确保是列表格式
        species_ofp = data.get("species_ofp", [])
        if not isinstance(species_ofp, list):
            logger.warning("obm_conversion_species_not_list", species_type=type(species_ofp).__name__)
            species_ofp = []

        # 验证species_ofp数据格式
        validated_species = []
        for species in species_ofp:
            if isinstance(species, dict):
                validated_species.append({
                    "species": species.get("species", species.get("name", "Unknown")),
                    "concentration": float(species.get("concentration", species.get("conc", 0.0))),
                    "ofp": float(species.get("ofp", species.get("OFP", 0.0))),
                    "category": species.get("category", species.get("class", "Unknown"))
                })
            else:
                logger.warning("obm_conversion_skip_invalid_species", species=species)

        # 处理category_summary - 确保是列表格式
        category_summary = data.get("category_summary", [])
        if not isinstance(category_summary, list):
            logger.warning("obm_conversion_category_not_list", category_type=type(category_summary).__name__)
            category_summary = []

        # 转换category_summary为UnifiedVOCCategoryOFP格式
        unified_category = []
        for cat in category_summary:
            if isinstance(cat, dict):
                unified_category.append({
                    "category": cat.get("category", cat.get("class", "Unknown")),
                    "total_ofp": float(cat.get("total_ofp", cat.get("ofp", 0.0))),
                    "species_count": int(cat.get("species_count", cat.get("count", 0))),
                    "contribution_pct": float(cat.get("contribution_pct", cat.get("pct", 0.0)))
                })
            else:
                logger.warning("obm_conversion_skip_invalid_category", category=cat)

        # 处理carbon_summary - 确保是列表格式
        carbon_summary = data.get("carbon_summary", [])
        if not isinstance(carbon_summary, list):
            logger.warning("obm_conversion_carbon_not_list", carbon_type=type(carbon_summary).__name__)
            carbon_summary = []

        # 转换carbon_summary为UnifiedVOCCarbonOFP格式
        unified_carbon = []
        for carbon in carbon_summary:
            if isinstance(carbon, dict):
                unified_carbon.append({
                    "carbon_count": int(carbon.get("carbon_count", carbon.get("carbon", 0))),
                    "total_ofp": float(carbon.get("total_ofp", carbon.get("ofp", 0.0))),
                    "species_count": int(carbon.get("species_count", carbon.get("count", 0)))
                })
            else:
                logger.warning("obm_conversion_skip_invalid_carbon", carbon=carbon)

        # 处理sensitivity - 确保是字典格式
        sensitivity = data.get("sensitivity", {})
        if not isinstance(sensitivity, dict):
            logger.warning("obm_conversion_sensitivity_not_dict", sensitivity_type=type(sensitivity).__name__)
            sensitivity = {}

        # 处理timeseries - 确保是列表格式
        timeseries = data.get("timeseries", [])
        if not isinstance(timeseries, list):
            logger.warning("obm_conversion_timeseries_not_list", timeseries_type=type(timeseries).__name__)
            timeseries = []

        # 转换timeseries为UnifiedOBMOFPSample格式
        unified_timeseries = []
        for ts in timeseries:
            if isinstance(ts, dict):
                unified_timeseries.append({
                    "time": ts.get("time", ""),
                    "vocs_ofp": float(ts.get("vocs_ofp", ts.get("total_ofp", 0.0))),
                    "ozone_formation_potential": float(ts.get("ozone_formation_potential", ts.get("ofp", 0.0))),
                    "sensitivity_type": ts.get("sensitivity_type", ts.get("regime", "Unknown"))
                })
            else:
                logger.warning("obm_conversion_skip_invalid_timeseries", ts=ts)

        # 构建UnifiedOBMOFPData模型
        unified_result = UnifiedOBMOFPData(
            station_code=data.get("station_code", ""),
            station_name=station_name,
            species_ofp=validated_species,
            timeseries=unified_timeseries,
            category_summary=unified_category,
            carbon_summary=unified_carbon,
            sensitivity={
                "sensitivity_type": sensitivity.get("sensitivity_type", sensitivity.get("regime", "Unknown")),
                "vocs_control_effectiveness": float(sensitivity.get("vocs_control_effectiveness", sensitivity.get("vocs_eff", 0.0))),
                "nox_control_effectiveness": float(sensitivity.get("nox_control_effectiveness", sensitivity.get("nox_eff", 0.0))),
                "recommendation": sensitivity.get("recommendation", sensitivity.get("advice", ""))
            },
            total_ofp=float(data.get("total_ofp", 0.0)),
            primary_vocs=data.get("primary_vocs", data.get("key_species", [])),
            quality_report=data.get("quality_report"),
            metadata=data.get("metadata", {})
        )

        logger.info(
            "obm_conversion_complete",
            station_name=station_name,
            total_ofp=unified_result.total_ofp,
            species_count=len(validated_species),
            category_count=len(unified_category)
        )

        return [unified_result], "obm_ofp_result"

    except Exception as e:
        logger.error(
            "obm_conversion_failed",
            error=str(e),
            exc_info=True
        )
        return [], "error"


def validate_pmf_result_format(data: Any) -> Tuple[bool, List[str]]:
    """
    验证PMF结果格式

    Args:
        data: PMF结果数据

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    if not data:
        errors.append("PMF结果数据为空")
        return False, errors

    # 如果是列表，验证第一个元素
    if isinstance(data, list):
        if not data:
            errors.append("PMF结果列表为空")
            return False, errors
        data = data[0]

    if not isinstance(data, dict):
        errors.append(f"PMF结果必须是字典格式，实际为: {type(data).__name__}")
        return False, errors

    # 检查必要字段
    if "station_name" not in data:
        errors.append("缺少station_name字段")

    if "pollutant" not in data:
        errors.append("缺少pollutant字段")

    if "sources" not in data:
        errors.append("缺少sources字段")
    elif not isinstance(data["sources"], list):
        errors.append("sources字段必须是列表格式")

    # 验证sources数据
    if "sources" in data and isinstance(data["sources"], list):
        for i, source in enumerate(data["sources"]):
            if not isinstance(source, dict):
                errors.append(f"sources[{i}] 必须是字典格式")
                continue

            if "source_name" not in source and "source" not in source:
                errors.append(f"sources[{i}] 缺少source_name或source字段")

            if "contribution_pct" not in source and "contribution" not in source:
                errors.append(f"sources[{i}] 缺少contribution_pct或contribution字段")

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_obm_result_format(data: Any) -> Tuple[bool, List[str]]:
    """
    验证OBM/OFP结果格式

    Args:
        data: OBM/OFP结果数据

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    if not data:
        errors.append("OBM结果数据为空")
        return False, errors

    # 如果是列表，验证第一个元素
    if isinstance(data, list):
        if not data:
            errors.append("OBM结果列表为空")
            return False, errors
        data = data[0]

    if not isinstance(data, dict):
        errors.append(f"OBM结果必须是字典格式，实际为: {type(data).__name__}")
        return False, errors

    # 检查必要字段
    if "station_name" not in data:
        errors.append("缺少station_name字段")

    if "total_ofp" not in data:
        errors.append("缺少total_ofp字段")

    if "sensitivity" not in data:
        errors.append("缺少sensitivity字段")
    elif not isinstance(data["sensitivity"], dict):
        errors.append("sensitivity字段必须是字典格式")

    # 验证species_ofp数据
    if "species_ofp" in data:
        if not isinstance(data["species_ofp"], list):
            errors.append("species_ofp字段必须是列表格式")
        else:
            for i, species in enumerate(data["species_ofp"]):
                if not isinstance(species, dict):
                    errors.append(f"species_ofp[{i}] 必须是字典格式")

    # 验证category_summary数据
    if "category_summary" in data:
        if not isinstance(data["category_summary"], list):
            errors.append("category_summary字段必须是列表格式")

    is_valid = len(errors) == 0
    return is_valid, errors
