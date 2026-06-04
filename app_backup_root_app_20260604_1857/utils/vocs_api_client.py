"""
VOCs API Client (广东省VOCs超站API版本)
直接调用广东超站VOCs接口获取VOCs组分数据

API格式（GET请求）:
GET /api/supproduct/supoperation/ComponentVOC/GetComponentVOCAnalysis

Query Parameters:
- StationCodes: 站点编码（如 "1042b"）
- StartTime: 开始时间（如 "2025-01-01 00:00:00"）
- EndTime: 结束时间（如 "2025-01-02 00:00:00"）
- tableType: 统计类型（1=小时，2=日，3=月，5=年）
- TableType: 统计类型（同上，冗余参数）
- dataType: 数据类型（0=原始，1=终审，4=初审，5=复审）
- IsMark: 是否包含标识（true/false）
- timePoint: 时间点数组（可选）
- DetectionitemType: 仪器类型（固定值）
- skipCount: 跳过数量（分页）
- maxResultCount: 最大结果数（分页）

Headers:
- Authorization: Bearer {token}
- syscode: 系统编码

✅ 已集成Token验证机制（复用ParticulateTokenManager）
✅ 使用正确的API端点: http://113.108.142.147:20065
"""

import structlog
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode

from app.utils.particulate_token_manager import get_particulate_token_manager

logger = structlog.get_logger()


class VocApiClient:
    """VOCs API客户端（广东省超站API版本）"""

    def __init__(self):
        """初始化API客户端"""
        self.base_url = "http://113.108.142.147:20065"
        self.token_manager = get_particulate_token_manager()
        self.logger = logger

        # VOCs API端点
        self.voc_category_endpoint = "/api/supproduct/supoperation/ComponentVOC/GetComponentVOCAnalysis"
        self.voc_species_endpoint = "/api/supproduct/supoperation/ComponentVOC/GetSpeciesVOCAnalysis"

    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        token = self.token_manager.get_token()
        if not token:
            raise Exception("无法获取API Token，请检查认证配置")

        sys_code = self.token_manager._cfg.get("vocs_sys_code") or self.token_manager._cfg.get("sys_code") or "SunSup"

        return {
            "Authorization": f"Bearer {token}",
            "SysCode": sys_code,
            "syscode": sys_code,
            "Content-Type": "application/json"
        }

    def get_voc_categories(
        self,
        station_code: str,
        start_time: str,
        end_time: str,
        table_type: int = 2,
        data_type: int = 1,
        is_mark: bool = False
    ) -> Dict[str, Any]:
        """
        查询VOCs类别数据（烷烃、烯烃、炔烃、芳香烃、OVOCs等）

        Args:
            station_code: 站点编码，如 "1042b"
            start_time: 开始时间，如 "2025-01-01 00:00:00"
            end_time: 结束时间，如 "2025-01-02 00:00:00"
            table_type: 统计类型，1=小时，2=日，3=月，5=年
            data_type: 数据类型，0=原始，1=终审，4=初审，5=复审
            is_mark: 是否包含标识字段

        Returns:
            API响应，包含:
            - dataList: 时序数据列表
            - resultAvg: 平均值
            - resultDataProp: 占比数据
            - resultAvgProp: 平均占比
            - detectionItems: 检测项列表
        """
        self.logger.info(
            "voc_category_query_start",
            station_code=station_code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type,
            data_type=data_type
        )

        # 构建查询参数（使用最小参数集，避免超时）
        params = {
            "StationCodes": station_code,
            "StartTime": start_time,
            "EndTime": end_time,
            "tableType": table_type,
            "dataType": data_type,
            "IsMark": is_mark
        }

        # 构建完整URL
        url = f"{self.base_url}{self.voc_category_endpoint}?{urlencode(params)}"

        try:
            # 获取认证头
            headers = self._get_auth_headers()

            # 发送GET请求
            response = requests.get(url, headers=headers, timeout=30)

            # 检查响应状态
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }

            # 解析JSON响应
            api_response = response.json()

            # 检查业务状态
            if not api_response.get("success"):
                return {
                    "success": False,
                    "error": api_response.get("msg", "API返回失败"),
                    "api_response": api_response
                }

            # 成功返回
            return {
                "success": True,
                "api_response": api_response,
                "record_count": len(api_response.get("result", {}).get("dataList", []))
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "API请求超时"
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}"
            }

    def get_voc_species(
        self,
        station_code: str,
        start_time: str,
        end_time: str,
        table_type: int = 2,
        data_type: int = 1,
        is_mark: bool = False
    ) -> Dict[str, Any]:
        """
        查询VOCs物种数据（乙烷、乙烯、乙炔、丙烷等具体物种）

        Args:
            station_code: 站点编码，如 "1042b"
            start_time: 开始时间
            end_time: 结束时间
            table_type: 统计类型，1=小时，2=日，3=月，5=年
            data_type: 数据类型，0=原始，1=终审，4=初审，5=复审
            is_mark: 是否包含标识字段

        Returns:
            API响应，包含具体VOCs物种数据
        """
        self.logger.info(
            "voc_species_query_start",
            station_code=station_code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type,
            data_type=data_type
        )

        # 构建查询参数（使用最小参数集，避免超时）
        params = {
            "StationCodes": station_code,
            "StartTime": start_time,
            "EndTime": end_time,
            "tableType": table_type,
            "dataType": data_type,
            "IsMark": is_mark
        }

        # 构建完整URL
        url = f"{self.base_url}{self.voc_species_endpoint}?{urlencode(params)}"

        try:
            # 获取认证头
            headers = self._get_auth_headers()

            # 发送GET请求
            response = requests.get(url, headers=headers, timeout=30)

            # 检查响应状态
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }

            # 解析JSON响应
            api_response = response.json()

            # 检查业务状态
            if not api_response.get("success"):
                return {
                    "success": False,
                    "error": api_response.get("msg", "API返回失败"),
                    "api_response": api_response
                }

            # 成功返回
            return {
                "success": True,
                "api_response": api_response,
                "record_count": len(api_response.get("result", {}).get("dataList", []))
            }

        except Exception as e:
            self.logger.error("voc_species_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }


# 单例模式
_voc_api_client = None

def get_voc_api_client() -> VocApiClient:
    """获取VOCs API客户端单例"""
    global _voc_api_client
    if _voc_api_client is None:
        _voc_api_client = VocApiClient()
    return _voc_api_client
