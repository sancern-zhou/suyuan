"""
工具依赖关系定义

定义工具之间的依赖关系和参数绑定规则：
- 依赖关系：工具执行的先后顺序
- 参数绑定：如何从上游工具结果中提取参数值
- 绑定表达式：支持多种引用格式
"""

from typing import Dict, List, Any, Optional

# 工具依赖图定义（气象专家：专注气象 + 默认可视化）
TOOL_DEPENDENCY_GRAPHS = {
    "weather": {
        "description": "气象分析专家工具依赖（专注气象 + 默认可视化）",
        "tools": {
            # ========================================
            # 1. 核心气象工具（基础层）
            # ========================================
            "get_weather_data": {
                "depends_on": [],
                "produces": "weather_data",
                "output_fields": ["data_id", "metadata", "summary"],
                "timeout": 120,  # 数据库查询可能较慢，增加到120秒
                "description": "获取ERA5历史气象数据（基础数据源）",
                # 降级配置：当ERA5数据不可用（如当天数据）时，自动降级到通用气象工具
                "fallback": {
                    "tool": "get_universal_meteorology",
                    "condition": "data_empty_or_error",  # 触发条件：数据为空或查询错误
                    "param_mapping": {
                        # 源参数 -> 目标参数映射
                        "lat": "lat",
                        "lon": "lon",
                        # 额外参数（固定值）
                        "_defaults": {
                            "include_wind_profile": True,
                            "include_forecast": True,
                            "include_historical": False  # 历史数据已经失败，不再尝试
                        }
                    },
                    "description": "ERA5历史数据不可用时，降级到Open-Meteo实时/预报数据"
                }
            },

            "get_universal_meteorology": {
                "depends_on": [],
                "produces": "universal_weather_data",
                "output_fields": ["data_id", "data", "metadata"],
                "description": "通用气象数据接口（实时+预报，支持当天数据）",
                "requires_context": True  # 标记需要ExecutionContext
            },

            "get_current_weather": {
                "depends_on": [],
                "produces": "current_weather",
                "output_fields": ["data_id", "current_conditions"],
                "description": "当前实时天气数据"
            },

            "get_weather_forecast": {
                "depends_on": [],
                "produces": "weather_forecast",
                "output_fields": ["data_id", "forecast_data"],
                "description": "天气预报数据"
            },

            # ========================================
            # 2. 辅助气象工具（增强层）
            # ========================================
            "get_fire_hotspots": {
                "depends_on": [],
                "produces": "fire_hotspots_data",
                "output_fields": ["data_id", "hotspots"],
                "description": "火点数据（影响空气质量的气象因素）"
            },

            "get_dust_data": {
                "depends_on": [],
                "produces": "dust_data",
                "output_fields": ["data_id", "dust_info"],
                "description": "沙尘数据（气象传输）"
            },

            "get_satellite_data": {
                "depends_on": [],
                "produces": "satellite_data",
                "output_fields": ["data_id", "satellite_images"],
                "description": "卫星遥感数据"
            },

            # ========================================
            # 3. 专业分析工具（高级层）
            # ========================================
            "meteorological_trajectory_analysis": {
                "depends_on": ["get_weather_data"],
                "produces": "trajectory_result",
                "input_bindings": {
                    "lat": "{lat}",
                    "lon": "{lon}",
                    "start_time": "{start_time}",
                    "hours": 72  # 默认72小时后向轨迹
                },
                "output_fields": ["data_id", "trajectory_data", "dominant_direction"],
                "description": "后向轨迹分析（基于气象数据）",
                "timeout": 180.0  # NOAA HYSPLIT需要较长时间(40次轮询*3秒=120秒+网络延迟)
            },

            "trajectory_simulation": {
                "depends_on": ["get_weather_data", "meteorological_trajectory_analysis"],
                "produces": "simulation_result",
                "input_bindings": {
                    "lat": "{lat}",
                    "lon": "{lon}",
                    "trajectory_data_id": "meteorological_trajectory_analysis[FIRST].data_id"
                },
                "output_fields": ["data_id", "simulation_data"],
                "description": "轨迹模拟（预测传输路径）"
            },

            "analyze_upwind_enterprises": {
                "depends_on": ["get_weather_data", "meteorological_trajectory_analysis"],
                "produces": "enterprise_analysis",
                "input_bindings": {
                    "city_name": "{location}",
                    "weather_data_id": "$0.data_id"  # Context-Aware V2: $0 指向 get_weather_data，通过 data_id 获取风场数据
                },
                "output_fields": ["data_id", "analysis_result", "enterprises", "visuals"],
                "description": "上风向企业分析（基于传输路径，自动获取城市前3个国控站点）"
            },

            "analyze_trajectory_sources": {
                "depends_on": ["get_weather_data"],
                "produces": "trajectory_source_analysis",
                "input_bindings": {
                    "lat": "{lat}",
                    "lon": "{lon}",
                    "city_name": "{location}",
                    "mode": "backward",
                    "days": 2,
                    "pollutant": "{primary_pollutant or 'VOCs'}",
                    "search_radius_km": 5,
                    "top_n": 15
                },
                "output_fields": ["data_id", "top_contributors", "trajectory_summary", "visuals", "recommendations"],
                "description": "HYSPLIT轨迹+源清单深度溯源（3-5分钟）",
                "timeout": 600.0
            },

            # ========================================
            # 4. 默认可视化工具（核心层）
            # ========================================
            "smart_chart_generator": {
                "depends_on": ["get_weather_data"],
                "produces": "chart_visualization",
                "input_bindings": {
                    "data_id": "get_weather_data[FIRST].data_id",
                    "chart_purpose": "{chart_purpose or '气象数据可视化'}"
                },
                "output_fields": ["data_id", "chart_config", "visuals"],
                "description": "智能图表生成（默认可视化，自动选择图表类型）"
            },

            "generate_chart": {
                "depends_on": ["get_weather_data"],
                "produces": "custom_chart",
                "input_bindings": {
                    "weather_data_id": "get_weather_data[FIRST].data_id",
                    "chart_type": "{chart_type}",
                    "title": "{title or '气象数据分析图表'}"
                },
                "output_fields": ["data_id", "chart_config"],
                "description": "自定义图表生成（指定图表类型）"
            },

            "generate_map": {
                "depends_on": ["analyze_upwind_enterprises"],
                "produces": "map_visualization",
                "input_bindings": {
                    # 从analyze_upwind_enterprises获取站点和企业信息
                    "station": "analyze_upwind_enterprises[FIRST].analysis_result.station_info",
                    "enterprises": "analyze_upwind_enterprises[FIRST].enterprises",
                    "upwind_paths": "analyze_upwind_enterprises[FIRST].analysis_result.upwind_paths",
                    "sectors": "analyze_upwind_enterprises[FIRST].analysis_result.wind_sectors"
                },
                "output_fields": ["data_id", "chart_config", "visuals"],
                "description": "站点企业分布地图（基于analyze_upwind_enterprises结果生成）"
            },
        }
    },

    "component": {
        "description": "组分分析专家工具依赖",
        "tools": {
            # ========================================
            # VOCs数据查询（独立工具，端口9092）
            # ========================================
            "get_vocs_data": {
                "depends_on": [],
                "produces": "vocs_component_data",
                "output_fields": ["data_id", "data", "metadata", "summary"],
                "timeout": 120.0,  # VOCs数据获取需要较长时间（2分钟）
                "max_retries": 0  # 禁用重试机制，直接使用2分钟超时
            },
            # ========================================
            # 颗粒物数据查询（独立工具，端口9093）
            # 新增3个结构化查询工具，替代原get_particulate_data
            # ========================================
            "get_pm25_ionic": {
                "depends_on": [],
                "produces": "particulate_ionic_data",
                "output_fields": ["data_id", "data", "metadata", "summary"],
                "timeout": 120.0,
                "max_retries": 0
            },
            "get_pm25_carbon": {
                "depends_on": [],
                "produces": "particulate_carbon_data",
                "output_fields": ["data_id", "data", "metadata", "summary"],
                "timeout": 120.0,
                "max_retries": 0
            },
            "get_pm25_crustal": {
                "depends_on": [],
                "produces": "particulate_crustal_data",
                "output_fields": ["data_id", "data", "metadata", "summary"],
                "timeout": 120.0,
                "max_retries": 0
            },
            # ========================================
            # PMF源解析工具（仅用于颗粒物溯源）
            # 需要水溶性离子和碳组分数据
            # ========================================
            "calculate_pm_pmf": {
                "depends_on": ["get_pm25_ionic", "get_pm25_carbon"],
                "produces": "pmf_result",
                "input_bindings": {
                    # 水溶性离子数据（role=water-soluble，包含SO4、NO3、NH4等）
                    "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                    # 碳组分数据（role=carbon，包含OC、EC）- 用于识别燃烧源
                    "gas_data_id": "get_pm25_carbon[role=carbon].data_id",
                    "pollutant_type": "PM2.5",
                    "station_name": "get_pm25_ionic[role=water-soluble].metadata.station_name or {location}"
                },
                "output_fields": ["data_id", "factors", "source_contributions", "model_stats"],
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            # ========================================
            # VOCs PMF源解析工具（仅用于臭氧溯源）
            # 直接使用VOCs数据，不需要role
            # ========================================
            "calculate_vocs_pmf": {
                "depends_on": ["get_vocs_data"],
                "produces": "pmf_result",
                "input_bindings": {
                    "data_id": "get_vocs_data[FIRST].data_id",
                    "pollutant_type": "VOCs",
                    "station_name": "get_vocs_data[FIRST].metadata.station_name or {location}"
                },
                "output_fields": ["data_id", "factors", "source_contributions", "model_stats"],
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            # ========================================
            # 颗粒物组分分析工具（新增 - 依赖颗粒物数据）
            # 7大组分重构、碳组分、地壳元素、水溶性离子、微量元素
            #
            # 注意：get_particulate_data被调用4次，每次查询不同组分：
            # - index=1: 水溶性离子 (SO4, NO3, NH4, Ca, Cl, K, Mg, Na, F)
            # - index=2: 碳组分 (OC, EC)
            # - index=3: 地壳元素 (Al, Si, Fe, Ca, Ti, K, Mg, Na)
            # - index=4: 微量元素 (Zn, Pb, Cu, Cd, As, Se, Ni, Cr, Mn)
            #
            # 使用具体索引而非 [FIRST]，确保每个工具获取正确的数据类型
            # ============================================
            "calculate_reconstruction": {
                "depends_on": ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"],
                "produces": "reconstruction_result",
                "input_bindings": {
                    # 7大组分重构暂时禁用，由LLM直接基于原始数据分析
                    # 此处保留工具定义，但input_bindings为空
                    # "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                    # "data_id_carbon": "get_pm25_carbon[role=carbon].data_id",
                    # "data_id_crustal": "get_pm25_crustal[role=crustal].data_id",
                    # "data_id_trace": "get_pm25_crustal[role=trace].data_id",
                },
                "output_fields": ["data_id", "data", "visuals", "metadata"],
                "description": "PM2.5 7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）- 暂时禁用",
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            "calculate_carbon": {
                "depends_on": ["get_pm25_carbon"],
                "produces": "carbon_result",
                "input_bindings": {
                    # 碳组分数据（role=carbon，包含OC、EC）
                    "data_id": "get_pm25_carbon[role=carbon].data_id",
                    "carbon_type": "pm25",
                    "oc_to_om": 1.4,
                    "poc_method": "ec_normalization"
                },
                "output_fields": ["data_id", "data", "visuals", "metadata"],
                "description": "碳组分分析（POC、SOC、EC/OC比值）",
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            "calculate_soluble": {
                "depends_on": ["get_pm25_ionic"],
                "produces": "soluble_result",
                "input_bindings": {
                    # 水溶性离子数据（role=water-soluble，包含SO4、NO3、NH4等）
                    "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                    "analysis_type": "full"
                },
                "output_fields": ["data_id", "data", "visuals", "metadata"],
                "description": "水溶性离子分析（三元图、SOR/NOR、阴阳离子平衡）",
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            "calculate_crustal": {
                "depends_on": ["get_pm25_crustal"],
                "produces": "crustal_result",
                "input_bindings": {
                    # 地壳元素数据（role=crustal，包含Al、Si、Fe、Ca等）
                    "data_id": "get_pm25_crustal[role=crustal].data_id",
                    "reconstruction_type": "full"
                },
                "output_fields": ["data_id", "data", "visuals", "metadata"],
                "description": "地壳元素分析（氧化物转换、箱线图）",
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            "calculate_trace": {
                "depends_on": ["get_pm25_crustal"],
                "produces": "trace_result",
                "input_bindings": {
                    # 微量元素数据（role=trace，包含Zn、Pb、Cu等）
                    "data_id": "get_pm25_crustal[role=trace].data_id",
                    "al_column": "铝"
                },
                "output_fields": ["data_id", "data", "visuals", "metadata"],
                "description": "微量元素分析（铝归一化、Taylor丰度对比）",
                "requires_context": True  # 需要ExecutionContext加载数据
            },
            # ========================================
            # VOCs分析工具（依赖VOCs数据）
            # ========================================
            # 完整化学机理OBM（依赖VOCs数据）
        },
    },

    "viz": {
        "description": "可视化专家工具依赖",
        "tools": {
            "smart_chart_generator": {
                "depends_on": ["weather:*, component:*"],  # 依赖所有weather和component的结果
                "produces": "chart_visualization",
                "output_fields": ["data_id", "chart_config", "visuals"]
            },
            "generate_chart": {
                "depends_on": ["*"],  # 依赖所有上游结果
                "produces": "custom_chart",
                "output_fields": ["data_id", "chart_config"]
            },
            "generate_map": {
                "depends_on": ["analyze_upwind_enterprises"],  # 依赖上风向企业分析结果
                "produces": "map_visualization",
                "input_bindings": {
                    # 从analyze_upwind_enterprises获取站点和企业信息
                    "station": "analyze_upwind_enterprises[FIRST].analysis_result.station_info",
                    "enterprises": "analyze_upwind_enterprises[FIRST].enterprises",
                    "upwind_paths": "analyze_upwind_enterprises[FIRST].analysis_result.upwind_paths",
                    "sectors": "analyze_upwind_enterprises[FIRST].analysis_result.wind_sectors"
                },
                "output_fields": ["data_id", "chart_config", "visuals"]
            }
        }
    },

    "report": {
        "description": "报告专家不需要工具",
        "tools": {
            "generate_synthesis_report": {
                "depends_on": ["*"],  # 依赖所有上游结果
                "produces": "comprehensive_report",
                "output_fields": ["data_id", "report_content", "recommendations"]
            }
        }
    }
}

# 绑定表达式解析规则
BINDING_EXPRESSION_PATTERNS = {
    "indexed_tool": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]$",
        "description": "引用指定索引的工具结果，如：get_vocs_data[0]"
    },
    "role_based_tool": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[role=([a-zA-Z0-9_-]+)\]$",
        "description": "按角色引用工具结果，如：get_pm25_ionic[role=water-soluble]"
    },
    "role_based_field": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[role=([a-zA-Z0-9_-]+)\]\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*)$",
        "description": "按角色访问工具结果字段，如：get_pm25_ionic[role=water-soluble].data_id"
    },
    "field_access": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*)$",
        "description": "访问工具结果的字段，如：get_vocs_data[0].data_id 或 get_vocs_data[0].metadata.station_name"
    },
    "simple_index_field_access": {
        "pattern": r"^\$(\d+)\.(.+)$",
        "description": "简单索引字段访问，如：$2.payload.data.analyzed_stations[0]"
    },

    "first_matching_tool": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[FIRST\]$",
        "description": "第一个匹配的工具结果，如：get_vocs_data[FIRST]"
    },

    "first_matching_field": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[FIRST\]\.([a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*)$",
        "description": "第一个匹配的工具结果的字段，如：get_vocs_data[FIRST].data_id"
    },

    "context_field": {
        "pattern": r"^\{([a-zA-Z_][a-zA-Z0-9_]*)\}$",
        "description": "引用上下文字段，如：{location}, {lat}"
    },
    "context_nested": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.context\.([a-zA-Z_][a-zA-Z0-9_]*)$",
        "description": "访问工具执行上下文，如：get_weather_data[0].context.lat"
    },
    "wildcard": {
        "pattern": r"^([a-zA-Z_][a-zA-Z0-9_]*):\*$",
        "description": "通配符引用，如：weather:*, component:*"
    },
    "special_value": {
        "pattern": r"^auto_([a-zA-Z_][a-zA-Z0-9_]*)$",
        "description": "特殊自动解析值，如：{auto_generate}, {first_available}, {auto_pmf_data_id}"
    },
    "fallback_field": {
        "pattern": r"^(.+?)\s+or\s+\{(.+?)\}$",
        "description": "带fallback的字段访问，如：get_pm25_ionic[FIRST].metadata.station_name or {location}"
    },
    "simple_index": {
        "pattern": r"^\$(\d+)$",
        "description": "简单索引引用，如：$0, $1（引用工具结果的索引位置）"
    },
    # ========================================
    # 直接值模式（非绑定表达式，用于工具参数的固定值）
    # ========================================
    "literal_value": {
        "pattern": r"^(full|quick|standard|pm25|pm10|ec_normalization|clip|keep|all|none)$",
        "description": "直接值（非绑定表达式），如：full, pm25, ec_normalization"
    }
}

# 常见绑定表达式示例
COMMON_BINDING_EXAMPLES = {
    "data_id_extraction": [
        "get_vocs_data[0].data_id",
        "get_pm25_ionic[0].data_id",
        "get_air_quality[0].data_id",
        "weather_analysis[0].data_id"
    ],
    "metadata_extraction": [
        "get_vocs_data[0].metadata.station_name",
        "get_pm25_ionic[0].metadata.station_name",
        "get_air_quality[0].metadata.location",
        "pmf_result[0].factors[0].name"
    ],
    "context_extraction": [
        "get_weather_data[0].context.lat",
        "get_weather_data[0].context.lon",
        "get_weather_data[0].context.start_time"
    ],
    "special_values": [
        "{auto_generate}",  # 自动生成值
        "{first_available}",  # 第一个可用值
        "{location}",  # 位置信息
        "{lat}",  # 纬度
        "{lon}"  # 经度
    ]
}

# 工具输出字段映射
TOOL_OUTPUT_SCHEMAS = {
    "get_vocs_data": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["metadata", "summary"],
        "data_structure": {
            "data_id": "str - VOCs数据存储ID（端口9092）",
            "data": "List[Dict] - VOCs组分数据记录列表",
            "metadata": "Dict - 元数据信息，包含station_name等",
            "summary": "str - 摘要信息"
        }
    },
    "get_pm25_ionic": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["metadata", "summary"],
        "data_structure": {
            "data_id": "str - PM2.5水溶性离子数据存储ID",
            "data": "List[Dict] - 离子组分数据记录列表",
            "metadata": "Dict - 元数据信息，包含station_name等",
            "summary": "str - 摘要信息"
        }
    },
    "get_pm25_carbon": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["metadata", "summary"],
        "data_structure": {
            "data_id": "str - PM2.5碳组分数据存储ID",
            "data": "List[Dict] - 碳组分数据记录列表（OC/EC）",
            "metadata": "Dict - 元数据信息，包含station_name等",
            "summary": "str - 摘要信息"
        }
    },
    "get_pm25_crustal": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["metadata", "summary"],
        "data_structure": {
            "data_id": "str - PM2.5地壳/微量元素数据存储ID",
            "data": "List[Dict] - 地壳/微量元素数据记录列表",
            "metadata": "Dict - 元数据信息，包含station_name等",
            "summary": "str - 摘要信息"
        }
    },
    "get_weather_data": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["metadata", "summary"],
        "data_structure": {
            "data_id": "str - 气象数据存储ID",
            "data": "List[Dict] - 气象数据记录列表",
            "metadata": "Dict - 元数据信息",
            "summary": "str - 摘要信息"
        }
    },
    "get_current_weather": {
        "required_fields": ["data_id", "current_conditions"],
        "optional_fields": ["metadata"],
        "data_structure": {
            "data_id": "str - 当前天气数据ID",
            "current_conditions": "Dict - 当前天气条件",
            "metadata": "Dict - 元数据信息"
        }
    },
    "meteorological_trajectory_analysis": {
        "required_fields": ["data_id", "trajectory_data"],
        "optional_fields": ["dominant_direction", "total_distance_km"],
        "data_structure": {
            "data_id": "str - 轨迹分析结果ID",
            "trajectory_data": "Dict - 轨迹数据",
            "dominant_direction": "str - 主导风向",
            "total_distance_km": "float - 总传输距离(km)"
        }
    },
    "analyze_upwind_enterprises": {
        "required_fields": ["data_id", "analysis_result"],
        "optional_fields": ["enterprises"],
        "data_structure": {
            "data_id": "str - 分析结果ID",
            "analysis_result": "Dict - 分析结果",
            "enterprises": "List[Dict] - 上风向企业列表"
        }
    },
    "analyze_trajectory_sources": {
        "required_fields": ["data_id", "top_contributors", "trajectory_summary", "visuals"],
        "optional_fields": ["recommendations", "emission_summary"],
        "data_structure": {
            "data_id": "str - 深度溯源分析结果ID",
            "top_contributors": "List[Dict] - 贡献排名前N的企业列表",
            "trajectory_summary": "Dict - 轨迹分析摘要信息",
            "visuals": "List[Dict] - 可视化图表列表（轨迹热力图、企业分布图等）",
            "recommendations": "List[str] - 管控建议",
            "emission_summary": "Dict - 排放汇总信息"
        }
    },
    "calculate_pmf": {
        "required_fields": ["data_id", "factors"],
        "optional_fields": ["source_contributions", "model_stats"],
        "data_structure": {
            "data_id": "str - PMF分析结果ID",
            "factors": "List[Dict] - 源因子信息",
            "source_contributions": "List[Dict] - 源贡献率",
            "model_stats": "Dict - 模型统计信息"
        }
    },
    # ========================================
    # 颗粒物组分分析工具输出schema（新增）
    # ========================================
    "calculate_reconstruction": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["visuals", "metadata"],
        "data_structure": {
            "data_id": "str - 组分重构结果ID",
            "data": "List[Dict] - 重构后的组分数据（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）",
            "visuals": "List[Dict] - 堆积时间序列图",
            "metadata": "Dict - 元数据信息"
        }
    },
    "calculate_carbon": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["visuals", "metadata"],
        "data_structure": {
            "data_id": "str - 碳组分分析结果ID",
            "data": "List[Dict] - 碳组分数据（POC、SOC、EC、EC/OC比值）",
            "visuals": "List[Dict] - 时间序列图、散点图",
            "metadata": "Dict - 元数据信息"
        }
    },
    "calculate_soluble": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["visuals", "metadata"],
        "data_structure": {
            "data_id": "str - 水溶性离子分析结果ID",
            "data": "Dict - 电荷数据、三元坐标、SOR/NOR数据",
            "visuals": "List[Dict] - 时间序列图、三元图、SOR/NOR散点图、电荷平衡图",
            "metadata": "Dict - 元数据信息"
        }
    },
    "calculate_crustal": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["visuals", "metadata"],
        "data_structure": {
            "data_id": "str - 地壳元素分析结果ID",
            "data": "Dict - 氧化物转换数据、地壳物质汇总",
            "visuals": "List[Dict] - 时间序列图、箱线图",
            "metadata": "Dict - 元数据信息"
        }
    },
    "calculate_trace": {
        "required_fields": ["data_id", "data"],
        "optional_fields": ["visuals", "metadata"],
        "data_structure": {
            "data_id": "str - 微量元素分析结果ID",
            "data": "Dict - 铝归一化数据、Taylor丰度对比数据",
            "visuals": "List[Dict] - 柱状图（富集因子排序）",
            "metadata": "Dict - 元数据信息"
        }
    },
    "smart_chart_generator": {
        "required_fields": ["data_id", "chart_config"],
        "optional_fields": ["visuals"],
        "data_structure": {
            "data_id": "str - 图表配置ID",
            "chart_config": "Dict - 图表配置数据",
            "visuals": "List[Dict] - 可视化内容列表"
        }
    },
    "generate_chart": {
        "required_fields": ["data_id", "chart_config"],
        "optional_fields": [],
        "data_structure": {
            "data_id": "str - 图表配置ID",
            "chart_config": "Dict - 图表配置数据"
        }
    },
    "generate_synthesis_report": {
        "required_fields": ["data_id", "report_content"],
        "optional_fields": ["recommendations"],
        "data_structure": {
            "data_id": "str - 报告ID",
            "report_content": "Dict - 报告内容",
            "recommendations": "List[str] - 建议措施"
        }
    }
}

# 依赖解析配置
DEPENDENCY_RESOLUTION_CONFIG = {
    "max_retries": 3,  # 最大重试次数
    "timeout_seconds": 30,  # 工具执行超时
    "parallel_execution": {
        "enabled": True,
        "max_concurrent": 5  # 最大并发数
    },
    "error_handling": {
        "skip_optional": True,  # 可选工具失败时跳过
        "fallback_enabled": True,  # 启用降级策略
        "retry_failed": True  # 失败后重试
    }
}

def get_tool_dependency_graph(expert_type: str) -> Optional[Dict[str, Any]]:
    """获取指定专家类型的工具依赖图"""
    return TOOL_DEPENDENCY_GRAPHS.get(expert_type)

def get_tool_output_schema(tool_name: str) -> Optional[Dict[str, Any]]:
    """获取工具的输出schema"""
    return TOOL_OUTPUT_SCHEMAS.get(tool_name)

def validate_binding_expression(expression: str) -> bool:
    """验证绑定表达式是否有效"""
    import re
    for pattern_info in BINDING_EXPRESSION_PATTERNS.values():
        if re.match(pattern_info["pattern"], expression):
            return True
    return False

def parse_binding_expression(expression: str) -> Dict[str, Any]:
    """解析绑定表达式"""
    import re

    for pattern_name, pattern_info in BINDING_EXPRESSION_PATTERNS.items():
        match = re.match(pattern_info["pattern"], expression)
        if match:
            return {
                "type": pattern_name,
                "pattern": pattern_info["pattern"],
                "groups": match.groups(),
                "description": pattern_info["description"]
            }

    return {
        "type": "unknown",
        "pattern": None,
        "groups": (),
        "description": "未匹配的表达式"
    }

def get_common_binding_examples() -> Dict[str, List[str]]:
    """获取常见绑定表达式示例"""
    return COMMON_BINDING_EXAMPLES.copy()

