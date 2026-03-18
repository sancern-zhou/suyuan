"""
数据格式JSON Schema定义

用于自动验证系统中各种数据格式的正确性
"""

# =============================================================================
# VOCs数据Schema
# =============================================================================

VOCs_SAMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "station_code": {"type": "string"},
        "station_name": {"type": "string"},
        "timestamp": {
            "type": "string",
            "format": "date-time"
        },
        "unit": {
            "type": "string",
            "enum": ["ppb", "μg/m³", "ug/m3", "PPB", "PPBV"]
        },
        "species": {
            "type": "object",
            "patternProperties": {
                ".*": {"type": "number", "minimum": 0}
            },
            "minProperties": 3  # 至少3种物种
        },
        "qc_flag": {
            "anyOf": [
                {"type": "string", "enum": ["valid", "invalid", "estimated"]},
                {"type": "null"}
            ]
        },
        "metadata": {
            "anyOf": [
                {"type": "object"},
                {"type": "null"}
            ]
        }
    },
    "required": ["station_code", "station_name", "timestamp", "unit", "species"]
}

VOCS_ARRAY_SCHEMA = {
    "type": "array",
    "items": VOCs_SAMPLE_SCHEMA,
    "minItems": 1
}

# =============================================================================
# 颗粒物数据Schema
# =============================================================================

PARTICULATE_SAMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "station_code": {"type": "string"},
        "station_name": {"type": "string"},
        "timestamp": {
            "type": "string",
            "format": "date-time"
        },
        "unit": {
            "type": "string",
            "enum": ["μg/m³", "ug/m3", "ng/m³", "UGM3"]
        },
        "components": {
            "type": "object",
            "patternProperties": {
                ".*": {"type": "number", "minimum": 0}
            },
            "minProperties": 3
        },
        "qc_flag": {
            "anyOf": [
                {"type": "string", "enum": ["valid", "invalid", "estimated"]},
                {"type": "null"}
            ]
        }
    },
    "required": ["station_code", "station_name", "timestamp", "unit", "components"]
}

# =============================================================================
# PMF结果Schema
# =============================================================================

PMF_SOURCE_CONTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "source_name": {"type": "string"},
        "contribution_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "concentration": {"type": "number", "minimum": 0},
        "confidence": {
            "type": "string",
            "enum": ["High", "Medium", "Low", "High", "Medium", "Low"]
        }
    },
    "required": ["source_name", "contribution_pct", "concentration", "confidence"]
}

PMF_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "pollutant": {
            "type": "string",
            "enum": ["VOCs", "PM2.5", "PM10", "PM"]
        },
        "station_name": {"type": "string"},
        "station_code": {"type": "string"},
        "schema_version": {"type": "string", "enum": ["pmf.v1"]},
        "sources": {
            "type": "array",
            "items": PMF_SOURCE_CONTRIBUTION_SCHEMA,
            "minItems": 1
        },
        "timeseries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "format": "date-time"},
                    "source_values": {
                        "type": "object",
                        "patternProperties": {
                            ".*": {"type": "number"}
                        }
                    }
                }
            }
        },
        "performance": {
            "type": "object",
            "properties": {
                "R2": {"type": "number", "minimum": 0, "maximum": 1},
                "RMSE": {"type": "number", "minimum": 0}
            }
        },
        "quality_report": {
            "type": "object"
        },
        "metadata": {
            "type": "object"
        }
    },
    "required": [
        "pollutant",
        "station_name",
        "schema_version",
        "sources",
        "timeseries",
        "performance"
    ]
}

# =============================================================================
# 图表配置Schema
# =============================================================================

CHART_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["pie", "bar", "line", "timeseries", "radar", "scatter", "heatmap"]
        },
        "title": {"type": "string"},
        "payload": {
            "type": "object",
            "properties": {
                "series": {"type": "array"},
                "x": {"type": "array"},
                "y": {
                    "anyOf": [
                        {"type": "array"},
                        {"type": "array", "items": {"type": "number"}}
                    ]
                }
            }
        },
        "meta": {
            "type": "object",
            "properties": {
                "data_source": {"type": "string"},
                "unit": {"type": "string"},
                "source": {"type": "string"}
            }
        },
        "mode": {
            "type": "string",
            "enum": ["normal", "compare"]
        }
    },
    "required": ["id", "type", "title", "payload"]
}

# =============================================================================
# 工具返回格式Schema
# =============================================================================

TOOL_SUCCESS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data_id": {
            "anyOf": [
                {"type": "string", "pattern": "^[a-z]+:v1:[a-f0-9]+$"},
                {"type": "null"}
            ]
        },
        "record_count": {"type": "integer", "minimum": 0},
        "summary": {"type": "string"},
        "detailed_summary": {"type": "string"},
        # 图表工具特有字段
        "type": {
            "anyOf": [
                {"type": "string", "enum": ["pie", "bar", "line", "timeseries", "radar"]},
                {"type": "null"}
            ]
        },
        "payload": {"type": "object"},
        "meta": {"type": "object"}
    },
    "required": ["success"]
}

TOOL_ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [False]},
        "error": {"type": "string"},
        "summary": {"type": "string"},
        "data_id": {"type": "null"},
        "available_fields": {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"}
            ]
        }
    },
    "required": ["success", "error", "summary"]
}

# =============================================================================
# Context存储格式Schema
# =============================================================================

CONTEXT_DATA_HANDLE_SCHEMA = {
    "type": "object",
    "properties": {
        "data_id": {"type": "string"},
        "schema": {
            "type": "string",
            "enum": ["vocs", "particulate", "weather", "pmf_result", "chart_config"]
        },
        "record_count": {"type": "integer", "minimum": 0},
        "data": {},
        "metadata": {"type": "object"}
    },
    "required": ["data_id", "schema", "record_count"]
}

# =============================================================================
# 数据ID格式验证
# =============================================================================

DATA_ID_REGEX = r'^[a-z_]+:v[0-9]+:[a-f0-9]{32}$'

# =============================================================================
# 工具调用参数Schema
# =============================================================================

GET_COMPONENT_DATA_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "station_name": {"type": "string"},
        "pollutant_type": {
            "type": "string",
            "enum": ["VOCs", "PM2.5", "PM10"]
        },
        "start_time": {"type": "string"},
        "end_time": {"type": "string"}
    },
    "required": ["query", "station_name", "pollutant_type"]
}

CALCULATE_PMF_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "station_name": {"type": "string"},
        "data_id": {
            "type": "string",
            "pattern": DATA_ID_REGEX
        },
        "pollutant_type": {
            "type": "string",
            "enum": ["VOCs", "PM2.5", "PM10"]
        },
        "start_time": {"type": "string"},
        "end_time": {"type": "string"}
    },
    "required": ["station_name", "data_id", "pollutant_type"]
}

GENERATE_CHART_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "data": {"type": ["object", "array"]},
        "scenario": {
            "type": "string",
            "enum": ["vocs_analysis", "pm_analysis", "multi_indicator_timeseries", "regional_comparison", "custom"]
        },
        "chart_type_hint": {
            "type": "string",
            "enum": ["pie", "bar", "line", "timeseries", "heatmap", "scatter", "radar", "auto"]
        },
        "title": {"type": "string"},
        "pollutant": {"type": "string"},
        "station_name": {"type": "string"}
    },
    "required": ["data"]
}

# =============================================================================
# 前端图表数据Schema
# =============================================================================

FRONTEND_CHART_DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["pie", "bar", "line", "timeseries", "radar"]
        },
        "title": {"type": "string"},
        "payload": {
            "anyOf": [
                # 饼图/柱状图
                {
                    "type": "object",
                    "properties": {
                        "series": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "data": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "value": {"type": "number"}
                                            },
                                            "required": ["name", "value"]
                                        }
                                    }
                                },
                                "required": ["type", "data"]
                            }
                        }
                    }
                },
                # 时序图
                {
                    "type": "object",
                    "properties": {
                        "x": {"type": "array"},
                        "series": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "data": {"type": "array"}
                                },
                                "required": ["name", "data"]
                            }
                        }
                    }
                }
            ]
        },
        "meta": {
            "type": "object",
            "properties": {
                "data_source": {"type": "string"},
                "unit": {"type": "string"}
            }
        }
    },
    "required": ["type", "title", "payload"]
}

# =============================================================================
# 验证函数
# =============================================================================

def validate_vocs_sample(data):
    """验证VOCs样本数据"""
    from jsonschema import validate, ValidationError
    try:
        validate(instance=data, schema=VOCs_SAMPLE_SCHEMA)
        return True, None
    except ValidationError as e:
        return False, str(e)

def validate_pmf_result(data):
    """验证PMF结果数据"""
    from jsonschema import validate, ValidationError
    try:
        validate(instance=data, schema=PMF_RESULT_SCHEMA)
        return True, None
    except ValidationError as e:
        return False, str(e)

def validate_chart_config(data):
    """验证图表配置数据"""
    from jsonschema import validate, ValidationError
    try:
        validate(instance=data, schema=CHART_CONFIG_SCHEMA)
        return True, None
    except ValidationError as e:
        return False, str(e)

def validate_tool_response(data):
    """验证工具返回数据"""
    from jsonschema import validate, ValidationError
    try:
        if data.get("success"):
            validate(instance=data, schema=TOOL_SUCCESS_RESPONSE_SCHEMA)
        else:
            validate(instance=data, schema=TOOL_ERROR_RESPONSE_SCHEMA)
        return True, None
    except ValidationError as e:
        return False, str(e)

def validate_data_id(data_id):
    """验证data_id格式"""
    import re
    if re.match(DATA_ID_REGEX, data_id):
        return True
    return False

# =============================================================================
# Schema集合
# =============================================================================

ALL_SCHEMAS = {
    "vocs_sample": VOCs_SAMPLE_SCHEMA,
    "vocs_array": VOCS_ARRAY_SCHEMA,
    "particulate_sample": PARTICULATE_SAMPLE_SCHEMA,
    "pmf_result": PMF_RESULT_SCHEMA,
    "chart_config": CHART_CONFIG_SCHEMA,
    "tool_success_response": TOOL_SUCCESS_RESPONSE_SCHEMA,
    "tool_error_response": TOOL_ERROR_RESPONSE_SCHEMA,
    "context_data_handle": CONTEXT_DATA_HANDLE_SCHEMA,
    "frontend_chart_data": FRONTEND_CHART_DATA_SCHEMA,
    "get_component_data_args": GET_COMPONENT_DATA_ARGS_SCHEMA,
    "calculate_pmf_args": CALCULATE_PMF_ARGS_SCHEMA,
    "generate_chart_args": GENERATE_CHART_ARGS_SCHEMA
}
