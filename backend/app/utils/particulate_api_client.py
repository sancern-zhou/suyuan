"""
Particulate Matter API Client (广东省颗粒物API版本)
使用ElementCompositionAnalysis API进行颗粒物组分数据查询

API格式（POST请求）:
{
  "StationCodes": ["1042b"],
  "pageCode": "element-lonic-analysis",
  "timePoint": ["2025-01-01 00:00:00", "2025-01-02 00:00:00"],
  "dataType": 0,  # 0=原始实况, 1=审核实况
  "hasMark": false,
  "dateType": 2,  # 2=Day, 3=Hour
  "DetectionItem": [],
  "StartTime": "2025-01-01 00:00:00",
  "EndTime": "2025-01-02 00:00:00",
  "skipCount": 0,
  "maxResultCount": 20
}

✅ 已集成Token验证机制（参考 vanna广东省颗粒物 项目）
✅ 使用正确的API端点: http://113.108.142.147:20065
"""

import structlog
import requests
import json
from typing import Dict, Any, Optional, List

from app.utils.particulate_token_manager import get_particulate_token_manager

logger = structlog.get_logger()


class ParticulateAPIClient:
    """颗粒物API客户端（广东省颗粒物API版本）✅ 已集成Token验证"""

    def __init__(self):
        """初始化API客户端"""
        self.base_url = "http://113.108.142.147:20065"
        self.token_manager = get_particulate_token_manager()
        self.logger = logger

        # API端点
        self.ionic_endpoint = "/api/supproduct/supoperation/ElementCompositionAnalysis/GetChartAnalysis"
        self.carbon_endpoint = "/api/supproduct/supoperation/ComponentPm25/GetComponentPm25Analysis"

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

    def get_ionic_analysis(
        self,
        station: str,
        code: str,
        start_time: str,
        end_time: str,
        time_type: int = 1,
        data_type: int = 0
    ) -> Dict[str, Any]:
        """
        查询水溶性离子数据

        Args:
            station: 站点名称，如 "新兴"
            code: 站点编码，如 "1042b"
            start_time: 开始时间，如 "2025-01-01 00:00:00"
            end_time: 结束时间，如 "2025-01-02 00:00:00"
            time_type: 时间粒度，1=hour, 2=day, 3=month, 5=year
            data_type: 数据类型，0=原始实况, 1=审核实况

        Returns:
            API响应
        """
        # 构建请求参数
        # 注意：离子分析API有两个dataType参数
        # - 第一个dataType（data_type参数）: 数据质量，0=原始，1=审核
        # - 第二个dataType（time_type参数）: 时间粒度，1=小时，2=日，3=月，5=年
        # 但API实际字段名是 dateType 和 dataType（参考api_unified_prompt.yaml）

        self.logger.info(f"[ParticulateAPI] 离子分析参数 - time_type(时间粒度)={time_type}, data_type(数据质量)={data_type}")

        payload = {
            "StationCodes": [code],
            "pageCode": "element-lonic-analysis",
            "timePoint": [start_time, end_time],
            "dataType": data_type,        # 数据质量：0=原始，1=审核
            "hasMark": False,
            "dateType": time_type,        # 时间粒度：1=小时，2=日，3=月，5=年
            "DetectionItem": [],
            "StartTime": start_time,
            "EndTime": end_time,
            "skipCount": 0,
            "maxResultCount": 1000  # 足够大的值以获取所有数据
        }

        return self._call_api(self.ionic_endpoint, payload)

    def get_carbon_components(
        self,
        station: str,
        code: str,
        start_time: str,
        end_time: str,
        table_type: int = 1,
        detection_item_codes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        查询碳组分数据（OC, EC）

        Args:
            station: 站点名称
            code: 站点编码
            start_time: 开始时间
            end_time: 结束时间
            table_type: 时间粒度 (1=小时, 2=日, 3=月, 5=年)
            detection_item_codes: OC/EC因子编码列表，默认使用标准编码

        Returns:
            API响应
        """
        # OC/EC因子编码 (根据API文档)
        # a340101 = OC（有机碳）
        # a340091 = EC（元素碳）
        # a34004 = PM2.5
        if detection_item_codes is None:
            detection_item_codes = ["a340101", "a340091", "a34004"]

        payload = {
            "StationCodes": [code],
            "timePoint": [start_time, end_time],
            "dataType": 0,        # 数据质量：0=原始，1=审核
            "IsMark": False,      # 修复：使用 IsMark（大写I）参考 vanna 项目
            "tableType": table_type,  # 时间粒度：1=小时，2=日，3=月，5=年
            "DetectionitemCodes": detection_item_codes,  # OC/EC因子编码（必填）
            "StartTime": start_time,
            "EndTime": end_time,
            "skipCount": 0,
            "maxResultCount": 1000
        }

        return self._call_api(self.carbon_endpoint, payload)

    def get_heavy_metal_analysis(
        self,
        station: str,
        code: str,
        start_time: str,
        end_time: str,
        date_type: int = 1,      # 数据质量：0=原始，1=审核（地壳元素仅在审核数据中有数值）
        data_type: int = 0,       # 时间粒度：0=小时(数值), 1=小时, 2=日(字符串占位符), 3=月, 5=年
        detection_item_codes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        查询重金属/地壳元素数据

        Args:
            station: 站点名称
            code: 站点编码
            start_time: 开始时间
            end_time: 结束时间
            date_type: 数据质量 (0=原始, 1=审核) - 地壳元素数值仅在审核数据中可用
            data_type: 时间粒度 (0=小时返回数值, 2=日返回字符串占位符) - 必须使用0获取数值
            detection_item_codes: 元素因子编码列表

        Returns:
            API响应

        注意：地壳元素数据需要 date_type=1(审核) + data_type=0(小时) 才能返回数值数据
        """
        # 地壳元素/重金属因子编码 (根据API文档)
        # a20002=铝, a20119=硅, a20029=钙, a20111=铁, a20095=钛, a20068=钾
        if detection_item_codes is None:
            detection_item_codes = ["a20002", "a20119", "a20029", "a20111", "a20095", "a20068"]

        payload = {
            "StationCodes": [code],
            "timePoint": [start_time, end_time],
            "dateType": date_type,        # 数据质量：0=原始，1=审核
            "IsMark": False,             # 修复：使用 IsMark（大写I）参考 vanna 项目
            "dataType": data_type,         # 时间粒度：1=小时，2=日，3=月，5=年
            "DetectionItem": "",
            "DetectionitemCodes": detection_item_codes,  # 元素因子编码（必填）
            "StartTime": start_time,
            "EndTime": end_time,
            "skipCount": 0,
            "maxResultCount": 1000
        }

        # 重金属使用与离子相同的端点
        return self._call_api(self.ionic_endpoint, payload)

    def _call_api(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用API（带Token验证和重试）

        Args:
            endpoint: API端点
            payload: 请求参数

        Returns:
            API响应
        """
        url = f"{self.base_url}{endpoint}"

        try:
            # 获取认证头
            headers = self._get_auth_headers()

            self.logger.info(f"[ParticulateAPI] POST {url}")
            self.logger.info(f"[ParticulateAPI] Request Payload: {json.dumps(payload, ensure_ascii=False)}")

            # 发送POST请求
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=120  # 增加到120秒，处理大数据量查询
            )

            # 检查响应状态
            if response.status_code == 401:
                self.logger.warning("[ParticulateAPI] Token无效，刷新Token后重试...")
                self.token_manager.invalidate_token()
                headers = self._get_auth_headers()
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=120  # 增加到120秒
                )

            response.raise_for_status()
            data = response.json()

            self.logger.info(f"[ParticulateAPI] 响应成功: {data.get('success')}")

            return {
                "success": True,
                "api_response": data,
                "status_code": response.status_code
            }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"[ParticulateAPI] 请求失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "api_response": None
            }
        except Exception as e:
            self.logger.error(f"[ParticulateAPI] 未知错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "api_response": None
            }


# 全局单例
_api_client: Optional[ParticulateAPIClient] = None


def get_particulate_api_client() -> ParticulateAPIClient:
    """获取全局API客户端实例（单例模式）"""
    global _api_client
    if _api_client is None:
        _api_client = ParticulateAPIClient()
    return _api_client


def reset_api_client():
    """重置全局API客户端（主要用于测试）"""
    global _api_client
    _api_client = None
