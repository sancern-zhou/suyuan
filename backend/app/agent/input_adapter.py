"""
Input Adapter Engine

输入适配引擎 - 实现"宽进严出"的输入参数处理机制

核心功能：
1. 字段映射 (Field Mapping) - 规范化字段名
2. 规范化器 (Normalizers) - 时间格式、单位转换
3. 推断器 (Inferencers) - 缺失字段智能推断
4. 验证器 (Validators) - Schema 验证

Author: Claude Code
Version: 1.0.0
"""

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import structlog

from config.settings import settings

logger = structlog.get_logger()


# ========================================
# 异常定义
# ========================================

class InputValidationError(Exception):
    """
    输入验证错误异常

    当工具参数缺失、格式错误或验证失败时抛出此异常。
    包含详细的错误信息和修复建议，供 Reflexion 系统使用。
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        error_type: str = "VALIDATION_FAILED",
        missing_fields: Optional[List[str]] = None,
        invalid_fields: Optional[Dict[str, str]] = None,
        expected_schema: Optional[Dict[str, Any]] = None,
        suggested_call: Optional[Dict[str, Any]] = None
    ):
        """
        初始化输入验证错误

        Args:
            message: 错误消息
            tool_name: 工具名称
            error_type: 错误类型
            missing_fields: 缺失的字段列表
            invalid_fields: 无效字段及原因
            expected_schema: 期望的参数 schema
            suggested_call: 修正建议
        """
        self.message = message
        self.tool_name = tool_name
        self.error_type = error_type
        self.missing_fields = missing_fields or []
        self.invalid_fields = invalid_fields or {}
        self.expected_schema = expected_schema or {}
        self.suggested_call = suggested_call or {}

        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": self.message,
            "error_type": self.error_type,
            "tool_name": self.tool_name,
            "missing_fields": self.missing_fields,
            "invalid_fields": self.invalid_fields,
            "expected_schema": self.expected_schema,
            "suggested_call": self.suggested_call
        }


# ========================================
# 工具规则配置
# ========================================

TOOL_RULES = {
    "get_weather_data": {
        "required_fields": ["data_type", "start_time", "end_time"],
        "optional_fields": ["lat", "lon", "station_id", "location_name"],
        "field_mapping": {
            "location": "location_name",  # location 映射到 location_name
            "时间范围": "time_range",
            "开始时间": "start_time",
            "结束时间": "end_time"
        },
        "normalizers": {
            "start_time": "normalize_time",
            "end_time": "normalize_time"
        },
        "inferencers": {
            "data_type": "infer_weather_data_type",
            "lat": "infer_lat_from_location",
            "lon": "infer_lon_from_location",
            "station_id": "infer_station_id_from_location"
        },
        "examples": {
            "era5": {"data_type": "era5", "lat": 23.13, "lon": 113.26, "start_time": "2025-11-07T00:00:00", "end_time": "2025-11-08T00:00:00"},
            "observed": {"data_type": "observed", "station_id": "GZ001", "start_time": "2025-11-07T00:00:00", "end_time": "2025-11-08T00:00:00"}
        }
    },
    "get_weather_forecast": {
        "required_fields": ["lat", "lon"],
        "optional_fields": ["location_name", "forecast_days", "past_days", "hourly", "daily"],
        "field_mapping": {
            "location": "location_name",
            "城市": "location_name",
            "city": "location_name"
        },
        "inferencers": {
            "lat": "infer_lat_from_location",
            "lon": "infer_lon_from_location"
        },
        "examples": {
            "with_city": {"location_name": "广州", "forecast_days": 7},
            "with_coords": {"lat": 23.13, "lon": 113.26, "forecast_days": 7},
            "with_past_days": {"location_name": "深圳", "past_days": 1, "forecast_days": 7}
        }
    },
    "get_air_quality": {
        "required_fields": ["question"],
        "optional_fields": [],
        "field_mapping": {
            "查询": "question",
            "问题": "question",
            "city": None,  # city 需要合并到 question
            "time_range": None  # time_range 需要合并到 question
        },
        "normalizers": {
            "question": "normalize_question"
        },
        "inferencers": {
            "question": "infer_question_from_parts"
        },
        "examples": {
            "simple": {"question": "查询广州今日空气质量"}
        }
    },
    "analyze_upwind_enterprises": {
        "required_fields": ["weather_data_id"],
        "conditional_required": {
            "city_name": {
                "condition": "station_name is None",
                "message": "city_name 和 station_name 必须提供其中一个"
            }
        },
        "optional_fields": ["station_name", "search_range_km", "max_enterprises", "top_n", "map_type", "mode"],
        "field_mapping": {
            "站点": "station_name",
            "station": "station_name",
            "站点名称": "station_name",
            "气象数据ID": "weather_data_id",
            "data_id": "weather_data_id"
        },
        "normalizers": {
            "search_range_km": "normalize_float"
        },
        "inferencers": {
            "search_range_km": "infer_default_search_range",
            "max_enterprises": "infer_default_max_enterprises",
            "top_n": "infer_default_top_n",
            "map_type": "infer_default_map_type",
            "mode": "infer_default_mode"
        },
        "examples": {
            "typical": {
                "city_name": "清远市",
                "station_name": "广雅中学",
                "weather_data_id": "weather:v1:xxx",
                "search_range_km": 5.0,
                "max_enterprises": 10,
                "top_n": 8,
                "map_type": "normal",
                "mode": "topn_mixed"
            }
        }
    },
    "generate_chart": {
        "required_fields": ["data"],
        "optional_fields": ["title", "chart_type_hint", "scenario", "pollutant", "station_name", "venue_name", "x_field", "y_field", "meta"],
        "field_mapping": {
            "数据": "data",
            "标题": "title",
            "图表类型": "chart_type_hint",
            "场景": "scenario",
            "污染物": "pollutant",
            "站点": "station_name",
            "场地": "venue_name",
            "records": "data"  # ✅ LLM可能直接用records作为字段名，需要映射到data
        },
        "normalizers": {
            "data": "normalize_chart_data"
        },
        "inferencers": {
            "data": "infer_data_from_context",
            "title": "infer_chart_title",
            "scenario": "infer_chart_scenario",
            "x_field": "infer_x_field_from_data",
            "y_field": "infer_y_field_from_data",
            "pollutant": "infer_pollutant_from_context",
            "station_name": "infer_station_name_from_context"
        },
        "examples": {
            "data_id_reference": {
                "data": {"data_ref": "data_0"},
                "scenario": "multi_indicator_timeseries",
                "pollutant": "O3",
                "station_name": "目标站点"
            },
            "direct_data": {
                "data": [{"time": "2025-11-07T00:00:00", "AQI": 45, "O3": 120}],
                "scenario": "custom",
                "title": "数据趋势图"
            },
            "vocs_analysis": {
                "data": {"data_ref": "data_1"},
                "scenario": "vocs_analysis",
                "title": "VOCs分析"
            }
        }
    },
    # ========================================
    # PMF源解析工具（颗粒物专用）
    # ========================================
    "calculate_pm_pmf": {
        "required_fields": ["station_name", "data_id", "gas_data_id"],
        "optional_fields": ["start_time", "end_time", "analysis_mode", "nimfa_rank"],
        "field_mapping": {
            "站点": "station_name",
            "站点名称": "station_name",
            "数据ID": "data_id",
            "气体数据ID": "gas_data_id",
            "component_data": "data_id",
            "data_ref": "data_id",
            "gas_data_ref": "gas_data_id"
        },
        "normalizers": {},
        "inferencers": {},
        "examples": {
            "pm25": {
                "station_name": "从化天湖",
                "data_id": "particulate_unified:v1:xxx",
                "gas_data_id": "particulate_unified:v1:yyy",
                "analysis_mode": "dual",
                "nimfa_rank": 5
            }
        }
    },
    # ========================================
    # PMF源解析工具（VOCs专用 - 仅用于臭氧溯源）
    # ========================================
    "calculate_vocs_pmf": {
        "required_fields": ["station_name", "data_id"],
        "optional_fields": ["start_time", "end_time", "analysis_mode", "nimfa_rank"],
        "field_mapping": {
            "站点": "station_name",
            "站点名称": "station_name",
            "数据ID": "data_id",
            "vocs数据ID": "data_id",
            "component_data": "data_id",
            "data_ref": "data_id"
        },
        "normalizers": {},
        "inferencers": {},
        "examples": {
            "vocs": {
                "station_name": "阳江市",
                "data_id": "vocs_unified:v1:abc123",
                "analysis_mode": "dual",
                "nimfa_rank": 5
            }
        }
    },
    # ========================================
    # ========================================
    # 气象轨迹分析工具 (NOAA HYSPLIT)
    # ========================================
    "meteorological_trajectory_analysis": {
        "required_fields": ["lat", "lon"],
        "optional_fields": ["start_time", "hours", "heights", "direction", "meteo_source", "location_name"],
        "field_mapping": {
            "latitude": "lat",
            "经度": "lon",
            "longitude": "lon",
            "纬度": "lat",
            "开始时间": "start_time",
            "起始时间": "start_time",
            "小时数": "hours",
            "回溯小时": "hours",
            "高度层": "heights",
            "方向": "direction",
            "轨迹方向": "direction",
            "气象数据源": "meteo_source",
            "location": "location_name",
            "城市": "location_name",
            "city": "location_name",
            "地点": "location_name"
        },
        "normalizers": {},
        "inferencers": {
            "lat": "infer_lat_from_location",
            "lon": "infer_lon_from_location"
        },
        "examples": {
            "with_station_name": {
                "location_name": "广州",
                "hours": 72,
                "direction": "Backward"
            },
            "with_coordinates": {
                "lat": 23.13,
                "lon": 113.26,
                "start_time": "2025-01-15T00:00:00Z",
                "hours": 72,
                "heights": [10, 500, 1000],
                "direction": "Backward",
                "meteo_source": "gdas1"
            },
            "minimal": {
                "lat": 23.13,
                "lon": 113.26
            }
        }
    },
}


# ========================================
# Input Adapter 引擎
# ========================================

class InputAdapterEngine:
    """
    输入适配引擎

    负责将 LLM 输出的"模糊参数"转换为工具需要的"严格参数"。

    工作流程：
    1. 字段映射：将各种变体字段名映射到标准字段
    2. 规范化：标准化时间格式、数值格式等
    3. 推断：智能推断缺失的字段
    4. 验证：检查所有必需字段是否完整
    """

    def __init__(self, tool_rules: Optional[Dict] = None):
        """
        初始化引擎

        Args:
            tool_rules: 自定义工具规则（可选，默认使用 TOOL_RULES）
        """
        self.tool_rules = tool_rules or TOOL_RULES
        logger.info("input_adapter_engine_initialized", tools_count=len(self.tool_rules))

    def normalize(
        self,
        tool_name: str,
        raw_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        规范化工具参数（主入口）

        Args:
            tool_name: 工具名称
            raw_args: 原始参数（来自 LLM）
            context: 可选的上下文信息（用于推断）

        Returns:
            (normalized_args, adapter_report)
            - normalized_args: 规范化后的参数
            - adapter_report: 适配过程报告

        Raises:
            InputValidationError: 验证失败时抛出
        """
        logger.info(
            "input_adapter_start",
            tool_name=tool_name,
            raw_args_keys=list(raw_args.keys())
        )

        # 检查工具是否有规则
        if tool_name not in self.tool_rules:
            logger.warning(
                "tool_has_no_rules",
                tool_name=tool_name,
                message="Using raw_args without adaptation"
            )
            return raw_args, {"status": "no_rules", "tool_name": tool_name}

        tool_rule = self.tool_rules[tool_name]
        normalized_args = raw_args.copy()
        adapter_report = {
            "tool_name": tool_name,
            "corrections": [],
            "inferences": [],
            "validations": []
        }

        try:
            # Step 1: 字段映射
            normalized_args = self._apply_field_mapping(
                normalized_args,
                tool_rule.get("field_mapping", {}),
                adapter_report
            )

            # Step 2: 规范化器
            normalized_args = self._apply_normalizers(
                normalized_args,
                tool_rule.get("normalizers", {}),
                adapter_report
            )

            # Step 3: 推断器
            normalized_args = self._apply_inferencers(
                normalized_args,
                tool_rule.get("inferencers", {}),
                tool_name,
                context,
                adapter_report
            )

            # Step 4: 验证器
            self._validate_required_fields(
                normalized_args,
                tool_rule.get("required_fields", []),
                tool_name,
                tool_rule,
                adapter_report
            )

            logger.info(
                "input_adapter_success",
                tool_name=tool_name,
                corrections_count=len(adapter_report["corrections"]),
                inferences_count=len(adapter_report["inferences"])
            )

            adapter_report["status"] = "success"
            return normalized_args, adapter_report

        except InputValidationError:
            # 验证错误直接抛出
            raise
        except Exception as e:
            logger.error(
                "input_adapter_failed",
                tool_name=tool_name,
                error=str(e),
                exc_info=True
            )
            # 其他错误包装为 InputValidationError
            raise InputValidationError(
                message=f"输入适配失败: {str(e)}",
                tool_name=tool_name,
                error_type="ADAPTER_ERROR"
            )

    def _apply_field_mapping(
        self,
        args: Dict[str, Any],
        field_mapping: Dict[str, Optional[str]],
        report: Dict
    ) -> Dict[str, Any]:
        """应用字段映射"""
        mapped_args = args.copy()

        for old_field, new_field in field_mapping.items():
            if old_field in mapped_args:
                if new_field:
                    # 重命名字段
                    mapped_args[new_field] = mapped_args.pop(old_field)
                    report["corrections"].append({
                        "type": "field_mapping",
                        "from": old_field,
                        "to": new_field
                    })
                else:
                    # 字段需要特殊处理（标记为待处理）
                    report["corrections"].append({
                        "type": "field_needs_processing",
                        "field": old_field,
                        "value": mapped_args[old_field]
                    })

        return mapped_args

    def _apply_normalizers(
        self,
        args: Dict[str, Any],
        normalizers: Dict[str, str],
        report: Dict
    ) -> Dict[str, Any]:
        """应用规范化器"""
        normalized_args = args.copy()

        for field, normalizer_name in normalizers.items():
            if field in normalized_args:
                try:
                    original_value = normalized_args[field]
                    normalized_value = self._call_normalizer(
                        normalizer_name,
                        original_value
                    )
                    normalized_args[field] = normalized_value

                    if original_value != normalized_value:
                        report["corrections"].append({
                            "type": "normalization",
                            "field": field,
                            "from": original_value,
                            "to": normalized_value
                        })
                except Exception as e:
                    logger.warning(
                        "normalization_failed",
                        field=field,
                        normalizer=normalizer_name,
                        error=str(e)
                    )

        return normalized_args

    def _apply_inferencers(
        self,
        args: Dict[str, Any],
        inferencers: Dict[str, str],
        tool_name: str,
        context: Optional[Dict],
        report: Dict
    ) -> Dict[str, Any]:
        """应用推断器"""
        inferred_args = args.copy()

        for field, inferencer_name in inferencers.items():
            # 只对缺失字段进行推断
            if field not in inferred_args or inferred_args[field] is None:
                try:
                    inferred_value = self._call_inferencer(
                        inferencer_name,
                        inferred_args,
                        tool_name,
                        context
                    )

                    if inferred_value is not None:
                        inferred_args[field] = inferred_value
                        report["inferences"].append({
                            "field": field,
                            "inferencer": inferencer_name,
                            "value": inferred_value
                        })
                except Exception as e:
                    logger.warning(
                        "inference_failed",
                        field=field,
                        inferencer=inferencer_name,
                        error=str(e)
                    )

        return inferred_args

    def _validate_required_fields(
        self,
        args: Dict[str, Any],
        required_fields: List[str],
        tool_name: str,
        tool_rule: Dict,
        report: Dict
    ):
        """验证必需字段"""
        missing_fields = [f for f in required_fields if f not in args or args[f] is None]

        # 处理条件必填字段
        conditional_required = tool_rule.get("conditional_required", {})
        for field, config in conditional_required.items():
            # 如果字段已存在且不为空，跳过
            if field in args and args[field] is not None:
                continue

            condition = config.get("condition", "")
            # 解析条件：当 station_name 为空时，city_name 是必填的
            if condition == "station_name is None":
                if "station_name" not in args or args["station_name"] is None:
                    # station_name 也缺失，此时 city_name 是必需的
                    missing_fields.append(field)

        if missing_fields:
            logger.error(
                "validation_failed_missing_fields",
                tool_name=tool_name,
                missing=missing_fields
            )

            # 生成修复建议
            suggested_call = self._generate_suggested_call(
                tool_name,
                args,
                missing_fields,
                tool_rule
            )

            raise InputValidationError(
                message=f"工具 {tool_name} 缺少必需参数: {', '.join(missing_fields)}",
                tool_name=tool_name,
                error_type="MISSING_REQUIRED_FIELDS",
                missing_fields=missing_fields,
                expected_schema=tool_rule,
                suggested_call=suggested_call
            )

        report["validations"].append({
            "type": "required_fields_check",
            "status": "passed",
            "required_fields": required_fields
        })

    def _call_normalizer(self, normalizer_name: str, value: Any) -> Any:
        """调用规范化器"""
        normalizer_map = {
            "normalize_time": self._normalize_time,
            "normalize_float": self._normalize_float,
            "normalize_question": self._normalize_question,
            "normalize_chart_data": self._normalize_chart_data
        }

        normalizer = normalizer_map.get(normalizer_name)
        if normalizer:
            return normalizer(value)

        logger.warning("normalizer_not_found", normalizer=normalizer_name)
        return value

    def _call_inferencer(
        self,
        inferencer_name: str,
        args: Dict[str, Any],
        tool_name: str,
        context: Optional[Dict]
    ) -> Optional[Any]:
        """调用推断器"""
        inferencer_map = {
            "infer_weather_data_type": lambda a, t, c: self._infer_weather_data_type(a),
            "infer_lat_from_location": lambda a, t, c: self._infer_lat_from_location(a),
            "infer_lon_from_location": lambda a, t, c: self._infer_lon_from_location(a),
            "infer_station_id_from_location": lambda a, t, c: self._infer_station_id_from_location(a),
            "infer_question_from_parts": lambda a, t, c: self._infer_question_from_parts(a),
            "infer_component_question": lambda a, t, c: self._infer_component_question(a),
            "infer_default_search_range": lambda a, t, c: 5.0,
            # 与 settings 中的默认值保持一致
            "infer_default_max_enterprises": lambda a, t, c: settings.default_max_enterprises,
            "infer_default_top_n": lambda a, t, c: settings.default_top_n_enterprises,
            "infer_default_map_type": lambda a, t, c: "normal",
            "infer_default_mode": lambda a, t, c: "topn_mixed",
            "infer_chart_title": lambda a, t, c: "数据分析图表",
            "infer_chart_scenario": lambda a, t, c: "custom",
            "infer_data_from_context": lambda a, t, c: self._infer_data_from_context(a, c),
            "infer_x_field_from_data": lambda a, t, c: self._infer_x_field_from_data(a),
            "infer_y_field_from_data": lambda a, t, c: self._infer_y_field_from_data(a),
            "infer_pollutant_from_context": lambda a, t, c: self._infer_pollutant_from_context(c),
            "infer_station_name_from_context": lambda a, t, c: self._infer_station_name_from_context(c)
        }

        inferencer = inferencer_map.get(inferencer_name)
        if inferencer:
            return inferencer(args, tool_name, context)

        logger.warning("inferencer_not_found", inferencer=inferencer_name)
        return None

    def _generate_suggested_call(
        self,
        tool_name: str,
        current_args: Dict[str, Any],
        missing_fields: List[str],
        tool_rule: Dict
    ) -> Dict[str, Any]:
        """生成修复建议"""
        suggested_args = current_args.copy()
        examples = tool_rule.get("examples", {})

        # 从示例中提取缺失字段的值
        if examples:
            example = list(examples.values())[0]
            for field in missing_fields:
                if field in example:
                    suggested_args[field] = f"<{example[field]}类型的值>"

        return {
            "tool": tool_name,
            "args": suggested_args,
            "missing": missing_fields,
            "examples": examples,
            "notes": f"请提供缺失的字段: {', '.join(missing_fields)}"
        }

    # ========================================
    # 规范化器实现
    # ========================================

    def _normalize_time(self, value: Any) -> str:
        """
        规范化时间格式（通用，使用ISO 8601）

        用于气象数据查询，保持 ISO 8601 格式 (YYYY-MM-DDTHH:MM:SS)
        """
        if isinstance(value, str):
            # 如果已经是 ISO 8601 格式，保持不变
            if "T" in value:
                return value
            # 如果包含空格，转换为 ISO 8601
            if " " in value:
                try:
                    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    return dt.strftime("%Y-%m-%dT%H:%M:%S")
                except:
                    pass
            # 其他情况保持原样
            return value
        return str(value)

    def _normalize_float(self, value: Any) -> float:
        """规范化浮点数"""
        try:
            return float(value)
        except:
            logger.warning("float_normalization_failed", value=value)
            return 0.0

    def _normalize_question(self, value: Any) -> str:
        """规范化问题文本"""
        if isinstance(value, str):
            return value.strip()
        return str(value)

    # ========================================
    # 推断器实现
    # ========================================

    def _infer_weather_data_type(self, args: Dict[str, Any]) -> Optional[str]:
        """推断天气数据类型"""
        if "lat" in args and "lon" in args:
            return "era5"
        elif "station_id" in args:
            return "observed"
        return None

    def _normalize_chart_data(self, value: Any) -> Any:
        """
        规范化图表数据格式

        策略：
        1. 如果是data_id字符串 (如 "data_0") → 转换为 {"data_ref": "data_0"}
        2. 如果是 {"data_ref": "data_X"} → 保持不变
        3. ✅ 如果是 {"records": [...]} → 转换为 UDF标准格式 [...]
        4. 如果是列表/字典数据 → 保持不变
        """
        logger.info(
            "normalize_chart_data_called",
            value_type=type(value).__name__,
            is_dict=isinstance(value, dict),
            has_records="records" in value if isinstance(value, dict) else False,
            has_data="data" in value if isinstance(value, dict) else False
        )

        if isinstance(value, str):
            # 检测data_id模式 (data_0, data_1, etc.)
            if value.startswith("data_") and value[5:].isdigit():
                logger.info(
                    "chart_data_normalized",
                    from_type="string",
                    to_type="data_ref",
                    data_id=value
                )
                return {"data_ref": value}

        # ✅ 处理非标准字段名 "records" (UDF规范使用 "data")
        if isinstance(value, dict) and "records" in value and "data" not in value:
            logger.warning(
                "chart_data_normalized_records_to_standard",
                message="LLM使用了非标准字段名'records'，已规范化为UDF v1.0标准格式",
                action="将records字段提取为数组",
                before_type=type(value).__name__,
                after_type="list"
            )
            # 提取records数组，返回标准格式
            records = value["records"]
            result = records if isinstance(records, list) else value
            logger.info(
                "chart_data_normalization_result",
                result_type=type(result).__name__,
                result_len=len(result) if isinstance(result, list) else "N/A"
            )
            return result

        # 已经是正确格式或原始数据，直接返回
        logger.info("chart_data_no_normalization_needed", value_type=type(value).__name__)
        return value

    def _infer_data_from_context(
        self,
        args: Dict[str, Any],
        context: Optional[Dict]
    ) -> Optional[Any]:
        """
        从上下文智能推断数据引用

        策略：
        1. 检查args中是否已经提供了data
        2. 如果未提供，从context中查找最近存储的数据
        3. 返回 {"data_ref": "data_X"} 格式
        """
        if not context:
            return None

        # 如果已经提供了data，不需要推断
        if "data" in args and args["data"]:
            return None

        # 尝试从context获取最新的data_id
        # 假设context有get_latest_data_id方法
        if hasattr(context, "get_latest_data_id"):
            latest_data_id = context.get_latest_data_id()
            if latest_data_id:
                logger.info(
                    "data_inferred_from_context",
                    data_id=latest_data_id,
                    source="context.get_latest_data_id"
                )
                return {"data_ref": latest_data_id}

        # 尝试从context的session_memory获取
        if hasattr(context, "session_memory"):
            session_memory = context.session_memory
            # 查找最近保存的数据ID (假设有list_data_ids方法)
            if hasattr(session_memory, "list_data_ids"):
                data_ids = session_memory.list_data_ids()
                if data_ids:
                    latest_data_id = data_ids[-1]  # 最新的ID
                    logger.info(
                        "data_inferred_from_session_memory",
                        data_id=latest_data_id,
                        total_ids=len(data_ids)
                    )
                    return {"data_ref": latest_data_id}

        logger.warning("data_inference_failed", reason="no_context_data_available")
        return None

    def _infer_x_field_from_data(self, args: Dict[str, Any]) -> Optional[str]:
        """
        从数据结构推断X轴字段名

        策略：
        1. 检查常见的时间字段名
        2. 检查常见的类别字段名
        """
        data = args.get("data")
        if not data:
            return None

        # 如果是data_ref，无法推断
        if isinstance(data, dict) and "data_ref" in data:
            return None

        # 如果是列表数据，检查第一条记录
        if isinstance(data, list) and len(data) > 0:
            first_record = data[0]
            if isinstance(first_record, dict):
                # 时间字段优先级
                time_fields = ["time", "timestamp", "timePoint", "date", "日期", "时间"]
                for field in time_fields:
                    if field in first_record:
                        logger.info("x_field_inferred", field=field, type="time")
                        return field

                # 类别字段
                category_fields = ["category", "name", "species", "组分", "类别"]
                for field in category_fields:
                    if field in first_record:
                        logger.info("x_field_inferred", field=field, type="category")
                        return field

        return None

    def _infer_y_field_from_data(self, args: Dict[str, Any]) -> Optional[str]:
        """
        从数据结构推断Y轴字段名

        策略：
        1. 检查常见的数值字段名
        2. 排除时间和类别字段
        """
        data = args.get("data")
        if not data:
            return None

        # 如果是data_ref，无法推断
        if isinstance(data, dict) and "data_ref" in data:
            return None

        # 如果是列表数据，检查第一条记录
        if isinstance(data, list) and len(data) > 0:
            first_record = data[0]
            if isinstance(first_record, dict):
                # 数值字段优先级
                value_fields = ["value", "concentration", "浓度", "val", "count"]
                for field in value_fields:
                    if field in first_record:
                        logger.info("y_field_inferred", field=field)
                        return field

                # 如果没有明确的value字段，尝试找数值类型字段
                for key, val in first_record.items():
                    if key not in ["time", "timestamp", "timePoint", "date", "category", "name"]:
                        if isinstance(val, (int, float)):
                            logger.info("y_field_inferred", field=key, source="numeric_field")
                            return key

        return None

    def _infer_pollutant_from_context(self, context: Optional[Dict]) -> Optional[str]:
        """
        从上下文推断污染物类型

        策略：
        1. 从上次查询的参数中提取
        2. 从数据中检测字段名
        """
        if not context:
            return None

        # 尝试从context获取污染物信息
        if hasattr(context, "get_query_params"):
            params = context.get_query_params()
            if isinstance(params, dict) and "pollutant" in params:
                pollutant = params["pollutant"]
                logger.info("pollutant_inferred_from_context", pollutant=pollutant)
                return pollutant

        # 默认返回O3（最常见的污染物）
        logger.info("pollutant_inferred_default", pollutant="O3")
        return "O3"

    def _infer_station_name_from_context(self, context: Optional[Dict]) -> Optional[str]:
        """
        从上下文推断站点名称

        策略：
        1. 从上次查询的参数中提取
        2. 从最新数据中提取
        """
        if not context:
            return None

        # 尝试从context获取站点信息
        if hasattr(context, "get_query_params"):
            params = context.get_query_params()
            if isinstance(params, dict):
                station_name = params.get("station_name") or params.get("station") or params.get("location")
                if station_name:
                    logger.info("station_name_inferred_from_context", station_name=station_name)
                    return station_name

        # 尝试从最新数据中提取
        if hasattr(context, "get_latest_data"):
            latest_data = context.get_latest_data()
            if isinstance(latest_data, list) and len(latest_data) > 0:
                first_record = latest_data[0]
                if isinstance(first_record, dict):
                    station_name = first_record.get("station_name") or first_record.get("站点名称")
                    if station_name:
                        logger.info("station_name_inferred_from_data", station_name=station_name)
                        return station_name

        logger.info("station_name_inferred_default", station_name="目标站点")
        return "目标站点"

    def _infer_lat_from_location(self, args: Dict[str, Any]) -> Optional[float]:
        """
        从location_name推断lat

        策略：
        1. 如果data_type=era5且提供了location_name，从映射表推断lat
        2. 如果工具是meteorological_trajectory_analysis，从映射表推断lat
        """
        data_type = args.get("data_type")
        location_name = args.get("location_name")

        # 城市坐标映射表
        # 数据来源：全国省市县乡四级政府驻地经纬度坐标 (http://gaohr.win/site/blogs/2022/2022-03-29-location-of-gov.html)
        CITY_COORDS_BASE = {
            # 广东省21个地级市
            "广州": (23.13, 113.26),
            "深圳": (22.54, 114.06),
            "珠海": (22.27, 113.58),
            "汕头": (23.35, 116.68),
            "佛山": (23.03, 113.12),
            "韶关": (24.81, 113.60),
            "湛江": (21.27, 110.36),
            "肇庆": (23.05, 112.47),
            "江门": (22.58, 113.08),
            "茂名": (21.66, 110.92),
            "惠州": (23.11, 114.42),
            "梅州": (24.29, 116.12),
            "汕尾": (22.79, 115.37),
            "河源": (23.74, 114.70),
            "阳江": (21.86, 111.98),
            "清远": (23.68, 113.06),
            "东莞": (23.02, 113.75),
            "中山": (22.52, 113.39),
            "潮州": (23.66, 116.62),
            "揭阳": (23.55, 116.37),
            "云浮": (22.92, 112.04),

            # 济宁市及辖区县
            "济宁": (35.42, 116.59),
            "任城区": (35.42, 116.59),
            "兖州区": (35.55, 116.83),
            "微山县": (34.81, 117.13),
            "鱼台县": (35.01, 116.65),
            "金乡县": (35.07, 116.31),
            "嘉祥县": (35.41, 116.34),
            "汶上县": (35.71, 116.49),
            "泗水县": (35.66, 117.27),
            "梁山县": (35.80, 116.10),

            # 广州市区
            "天河": (23.13, 113.36),
            "南山": (22.53, 113.93)
        }

        # 自动生成带"市"后缀的版本
        CITY_COORDS = {}
        for name, coords in CITY_COORDS_BASE.items():
            CITY_COORDS[name] = coords
            # 为地级市（2字名）添加"市"后缀
            if len(name) == 2 and not name.endswith(("区", "县")):
                CITY_COORDS[f"{name}市"] = coords

        # 判断是否可以使用坐标推断
        can_infer = (
            (data_type == "era5" and location_name) or  # ERA5气象数据
            location_name  # 任何工具提供location_name时都支持推断
        )

        if can_infer and location_name in CITY_COORDS:
            lat, _ = CITY_COORDS[location_name]
            logger.info("lat_inferred_from_location", location_name=location_name, lat=lat)
            return lat

        return None

    def _infer_lon_from_location(self, args: Dict[str, Any]) -> Optional[float]:
        """
        从location_name推断lon

        策略：
        1. 如果data_type=era5且提供了location_name，从映射表推断lon
        2. 如果工具是meteorological_trajectory_analysis，从映射表推断lon
        """
        data_type = args.get("data_type")
        location_name = args.get("location_name")

        # 城市坐标映射表
        # 数据来源：全国省市县乡四级政府驻地经纬度坐标 (http://gaohr.win/site/blogs/2022/2022-03-29-location-of-gov.html)
        CITY_COORDS_BASE = {
            # 广东省21个地级市
            "广州": (23.13, 113.26),
            "深圳": (22.54, 114.06),
            "珠海": (22.27, 113.58),
            "汕头": (23.35, 116.68),
            "佛山": (23.03, 113.12),
            "韶关": (24.81, 113.60),
            "湛江": (21.27, 110.36),
            "肇庆": (23.05, 112.47),
            "江门": (22.58, 113.08),
            "茂名": (21.66, 110.92),
            "惠州": (23.11, 114.42),
            "梅州": (24.29, 116.12),
            "汕尾": (22.79, 115.37),
            "河源": (23.74, 114.70),
            "阳江": (21.86, 111.98),
            "清远": (23.68, 113.06),
            "东莞": (23.02, 113.75),
            "中山": (22.52, 113.39),
            "潮州": (23.66, 116.62),
            "揭阳": (23.55, 116.37),
            "云浮": (22.92, 112.04),

            # 济宁市及辖区县
            "济宁": (35.42, 116.59),
            "任城区": (35.42, 116.59),
            "兖州区": (35.55, 116.83),
            "微山县": (34.81, 117.13),
            "鱼台县": (35.01, 116.65),
            "金乡县": (35.07, 116.31),
            "嘉祥县": (35.41, 116.34),
            "汶上县": (35.71, 116.49),
            "泗水县": (35.66, 117.27),
            "梁山县": (35.80, 116.10),

            # 广州市区
            "天河": (23.13, 113.36),
            "南山": (22.53, 113.93)
        }

        # 自动生成带"市"后缀的版本
        CITY_COORDS = {}
        for name, coords in CITY_COORDS_BASE.items():
            CITY_COORDS[name] = coords
            # 为地级市（2字名）添加"市"后缀
            if len(name) == 2 and not name.endswith(("区", "县")):
                CITY_COORDS[f"{name}市"] = coords

        # 判断是否可以使用坐标推断
        can_infer = (
            (data_type == "era5" and location_name) or  # ERA5气象数据
            location_name  # 任何工具提供location_name时都支持推断
        )

        if can_infer and location_name in CITY_COORDS:
            _, lon = CITY_COORDS[location_name]
            logger.info("lon_inferred_from_location", location_name=location_name, lon=lon)
            return lon

        return None

    def _infer_station_id_from_location(self, args: Dict[str, Any]) -> Optional[str]:
        """
        从location_name推断station_id

        策略：
        1. 如果data_type=observed且提供了location_name，从映射表推断station_id
        """
        data_type = args.get("data_type")
        location_name = args.get("location_name")

        # 城市站点ID映射表
        CITY_STATIONS = {
            "广州": "GZ_TIANHE_001",
            "深圳": "SZ_NANSHAN_001",
            "佛山": "FS_SHUNDE_001"
        }

        if data_type == "observed" and location_name and location_name in CITY_STATIONS:
            station_id = CITY_STATIONS[location_name]
            logger.info("station_id_inferred_from_location", location_name=location_name, station_id=station_id)
            return station_id

        return None

    def _infer_location_from_context(
        self,
        args: Dict[str, Any],
        context: Optional[Dict]
    ) -> Optional[Dict[str, Any]]:
        """
        从location_name推断lat/lon或station_id（已弃用，拆分为单独推断器）

        策略：
        1. 如果data_type=era5且提供了location_name，推断lat/lon
        2. 如果data_type=observed且提供了location_name，推断station_id
        """
        data_type = args.get("data_type")
        location_name = args.get("location_name")

        # 城市坐标映射表
        CITY_COORDS = {
            "广州": (23.13, 113.26),
            "深圳": (22.54, 114.06),
            "佛山": (23.03, 113.12),
            "佛山市": (23.03, 113.12),
            "天河": (23.13, 113.36),
            "南山": (22.53, 113.93)
        }

        # 城市站点ID映射表
        CITY_STATIONS = {
            "广州": "GZ_TIANHE_001",
            "深圳": "SZ_NANSHAN_001",
            "佛山": "FS_SHUNDE_001"
        }

        if not data_type or not location_name:
            return None

        # ERA5类型：推断lat/lon
        if data_type == "era5" and location_name in CITY_COORDS:
            lat, lon = CITY_COORDS[location_name]
            logger.info(
                "location_inferred_for_era5",
                location_name=location_name,
                lat=lat,
                lon=lon
            )
            return {"lat": lat, "lon": lon}

        # Observed类型：推断station_id
        if data_type == "observed" and location_name in CITY_STATIONS:
            station_id = CITY_STATIONS[location_name]
            logger.info(
                "station_id_inferred_for_observed",
                location_name=location_name,
                station_id=station_id
            )
            return {"station_id": station_id}

        logger.warning(
            "location_inference_failed",
            data_type=data_type,
            location_name=location_name,
            reason="未找到匹配的城市"
        )
        return None

    def _infer_question_from_parts(self, args: Dict[str, Any]) -> Optional[str]:
        """
        从碎片化参数构建完整问题

        策略：
        1. 合并city、time_range等字段到question
        """
        question = args.get("question", "")
        city = args.get("city")
        time_range = args.get("time_range")

        if city:
            question = f"{city}{question}" if question else city
        if time_range:
            question = f"{question}，{time_range}" if question else time_range

        return question if question else None

    def _infer_component_question(self, args: Dict[str, Any]) -> Optional[str]:
        """
        推断组分数据查询问题

        策略：
        1. 从location、time_range等构建问题
        """
        location = args.get("location")
        time_range = args.get("time_range")

        parts = []
        if location:
            parts.append(f"查询{location}")
        else:
            parts.append("查询")

        parts.append("组分数据")

        if time_range:
            parts.append(f"时间范围{time_range}")

        return "".join(parts)

    def _infer_obm_analysis_mode(self, args: Dict[str, Any]) -> Optional[str]:
        """
        推断增强OBM分析模式

        策略：
        1. 如果未指定，默认使用all模式
        2. 根据可用数据推断合适的模式
        """
        # 如果已经指定了模式，不需要推断
        if args.get("analysis_mode"):
            return None

        # 检查可用数据来推断模式
        has_nox = bool(args.get("nox_data_id"))
        has_o3 = bool(args.get("o3_data_id"))
        has_met = bool(args.get("meteorology_data_id"))

        # 如果有NOx和O3数据，使用all模式
        if has_nox and has_o3:
            logger.info("obm_analysis_mode_inferred", mode="all", reason="has_nox_and_o3")
            return "all"

        # 如果只有VOCs数据，默认使用rir模式
        if not has_nox and not has_o3:
            logger.info("obm_analysis_mode_inferred", mode="rir", reason="vocs_only")
            return "rir"

        # 默认使用all模式
        logger.info("obm_analysis_mode_inferred", mode="all", reason="default")
        return "all"


# ========================================
# 便捷函数
# ========================================

def normalize_tool_args(
    tool_name: str,
    raw_args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    规范化工具参数（便捷函数）

    Args:
        tool_name: 工具名称
        raw_args: 原始参数
        context: 可选的上下文

    Returns:
        (normalized_args, adapter_report)

    Raises:
        InputValidationError: 验证失败
    """
    adapter = InputAdapterEngine()
    return adapter.normalize(tool_name, raw_args, context)
