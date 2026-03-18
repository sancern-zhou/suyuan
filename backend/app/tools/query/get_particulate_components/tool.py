"""
PM2.5组分分析工具
对应参考项目中的 get_pm25_component_analysis 接口
支持组分：Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.particulate_api_client import get_particulate_api_client
from app.utils.geo_matcher import get_geo_matcher
from app.utils.particulate_token_manager import get_particulate_token_manager

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetParticulateComponentsTool(LLMTool):
    """PM2.5组分分析工具（参考项目模式）"""

    # PM2.5组分分析的固定 DetectionitemCodes 清单
    # 顺序固定：Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC
    DETECTION_ITEM_CODES = [
        "a36001",  # Cl⁻
        "a36002",  # NO₃⁻
        "a36003",  # SO₄²⁻
        "a36004",  # Na⁺
        "a36006",  # K⁺
        "a36005",  # NH₄⁺
        "a36007",  # Mg²⁺
        "a36008",  # Ca²⁺
        "a340101", # OC (有机碳)
        "a340091"  # EC (元素碳)
    ]

    # 组分名称映射（用于日志和提示）
    COMPONENT_NAMES = {
        "a36001": "Cl⁻",
        "a36002": "NO₃⁻",
        "a36003": "SO₄²⁻",
        "a36004": "Na⁺",
        "a36006": "K⁺",
        "a36005": "NH₄⁺",
        "a36007": "Mg²⁺",
        "a36008": "Ca²⁺",
        "a340101": "OC",
        "a340091": "EC"
    }

    def __init__(self) -> None:
        function_schema = {
            "name": "get_particulate_components",
            "description": (
                "Query PM2.5 component data (Cl⁻, NO₃⁻, SO₄²⁻, Na⁺, K⁺, NH₄⁺, Mg²⁺, Ca²⁺, OC, EC). "
                "This tool is designed for PMF source apportionment analysis requiring both "
                "ionic components (SO₄²⁻, NO₃⁻, NH₄⁺) and carbonaceous species (OC, EC). "
                "Uses fixed DetectionitemCodes list for standardized component analysis. "
                "Supports automatic location-to-code mapping using 'locations' parameter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Location names (city/station), e.g., ['东莞'], ['广州', '新兴']. Will be auto-mapped to StationCodes."
                    },
                    "station": {
                        "type": "string",
                        "description": "Station name in Chinese, e.g., '东莞', '揭阳', '新兴'. Use 'locations' for automatic mapping instead."
                    },
                    "code": {
                        "type": "string",
                        "description": "Station code, e.g., '1037b', '1042b'. Automatically mapped if 'locations' provided."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in format 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in format 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1, 4, 5, 7, 15],
                        "description": "Data type: 0=original, 1=audited (default: 0)"
                    },
                    "time_granularity": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "Time granularity: 1=hour, 2=day, 3=month, 5=year (default: 1)"
                    }
                },
                "required": ["start_time", "end_time"],
            },
        }

        super().__init__(
            name="get_particulate_components",
            description="Query PM2.5 component data for PMF analysis (10 components: ions + OC/EC).",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            requires_context=True,
        )

    async def execute(
        self,
        context: "ExecutionContext",
        start_time: str,
        end_time: str,
        locations: Union[List[str], None] = None,
        station: Union[str, None] = None,
        code: Union[str, None] = None,
        data_type: int = 0,
        time_granularity: int = 1,
        **_: Any
    ) -> Dict[str, Any]:
        """执行PM2.5组分分析查询"""

        # 参数处理：支持 locations 自动映射
        if locations:
            geo_matcher = get_geo_matcher()
            station_codes = geo_matcher.stations_to_codes(locations)
            if not station_codes:
                return {
                    "success": False,
                    "error": f"无法将 locations 映射到站点编码: {locations}",
                    "locations": locations
                }
            # 使用第一个映射的编码
            code = station_codes[0]
            # 尝试获取站点名称
            station = locations[0] if locations else station
        elif not (station and code):
            return {
                "success": False,
                "error": "必须提供 locations 参数，或者同时提供 station 和 code 参数"
            }

        logger.info(
            "pm25_component_analysis_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            time_granularity=time_granularity,
            components=self.DETECTION_ITEM_CODES,
            locations=locations
        )

        client = get_particulate_api_client()

        # 构建 question（参考项目模式）
        granularity_text = {1: "小时", 2: "日", 3: "月", 5: "年"}.get(time_granularity, "小时")
        component_list = "、".join([self.COMPONENT_NAMES.get(code, code) for code in self.DETECTION_ITEM_CODES])
        question = f"查询{station}{start_time[:10]}期间的{granularity_text}PM2.5组分数据，包含{component_list}"

        # 构建完整参数（参考项目模式）
        params = {
            "question": question,
            "Station": station,
            "Code": code,
            "DataType": data_type,
            "tableType": time_granularity,
            "StartTime": start_time,
            "EndTime": end_time,
            "timePoint": [start_time, end_time],
            "DetectionItem": "",
            "DetectionitemCodes": self.DETECTION_ITEM_CODES,
            "skipCount": 0,
            "maxResultCount": 1000
        }

        logger.debug("pm25_component_request_params", params=params)

        # 调用API - 使用token_manager获取正确的base_url
        import requests
        token_manager = get_particulate_token_manager()
        base_url = token_manager.get_base_url()
        url = f"{base_url}/api/uqp/query"

        try:
            headers = token_manager.get_auth_headers()
            response = requests.post(
                url,
                json=params,
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            api_response = response.json()

            # 提取记录
            records = []
            if isinstance(api_response, dict):
                result = api_response.get("data", {}).get("result", {})
                records = result.get("resultOne", [])

            if not records:
                return {
                    "success": False,
                    "error": "No component records found",
                    "station": station,
                    "code": code,
                    "requested_components": self.DETECTION_ITEM_CODES
                }

            # 保存数据
            data_ref = None
            file_path = None
            try:
                data_ref = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "pm25_components",
                        "station": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "data_type": data_type,
                        "time_granularity": time_granularity,
                        "detection_item_codes": self.DETECTION_ITEM_CODES
                    }
                )
                data_id = data_ref["data_id"]
                file_path = data_ref["file_path"]
                logger.info("pm25_components_saved", data_id=data_id, file_path=file_path, count=len(records))
            except Exception as save_error:
                logger.warning("pm25_components_save_failed", error=str(save_error))

            # 分析数据质量
            quality_report = self._analyze_quality(records)

            return {
                "success": True,
                "data": records,
                "count": len(records),
                "data_id": data_id,
                "file_path": file_path,
                "station": station,
                "code": code,
                "data_type": data_type,
                "time_granularity": time_granularity,
                "components": self.DETECTION_ITEM_CODES,
                "component_names": [self.COMPONENT_NAMES.get(code, code) for code in self.DETECTION_ITEM_CODES],
                "quality_report": quality_report,
                "summary": (
                    f"Retrieved {len(records)} PM2.5 component records for {station} ({code}), "
                    f"including {component_list}. Saved as {data_id} (path: {file_path})"
                )
            }

        except Exception as e:
            logger.error("pm25_component_analysis_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _analyze_quality(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析数据质量"""
        if not records:
            return {}

        first = records[0]

        # 检查PMF核心组分
        pmf_components = {
            "SO₄²⁻": "a36002",
            "NO₃⁻": "a36001",
            "NH₄⁺": "a36005",
            "OC": "a340101",
            "EC": "a340091"
        }

        component_stats = {}
        for name, code in pmf_components.items():
            if code in first:
                valid_count = sum(1 for r in records if r.get(code) not in ["—", "", None])
                component_stats[name] = {
                    "code": code,
                    "valid_count": valid_count,
                    "total": len(records),
                    "completeness": valid_count / len(records) if records else 0
                }

        # 统计所有可用组分字段
        all_component_fields = [
            k for k in first.keys()
            if k in self.DETECTION_ITEM_CODES or k in self.COMPONENT_NAMES.values()
        ]

        return {
            "total_records": len(records),
            "available_components": len(all_component_fields),
            "component_fields": all_component_fields,
            "pmf_components": component_stats,
            "pmf_ready": all(
                stats["completeness"] > 0.8  # 80%以上完整性
                for stats in component_stats.values()
            ) if component_stats else False
        }


def __init__() -> None:
    return GetParticulateComponentsTool()
