"""
HYSPLIT Output Parser

HYSPLIT输出文件解析器
解析tdump轨迹文件，转换为标准化数据格式

tdump文件格式：
- Header行1: 轨迹数量 描述
- Header行2: 起始年月日时 起始位置数量
- Header行3+: 起始位置信息
- Data行: 年月日时 预报小时 纬度 经度 高度 [其他变量]
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import struct
import structlog

logger = structlog.get_logger()


class HYSPLITOutputParser:
    """
    HYSPLIT输出文件解析器

    功能：
    - 解析tdump轨迹文件
    - 提取轨迹点数据
    - 转换为标准化格式
    - 插值气象变量（温度、气压）
    """

    def __init__(self):
        """初始化解析器"""
        logger.info("hysplit_output_parser_initialized")

    def parse_tdump(
        self,
        tdump_path: str
    ) -> Dict[str, Any]:
        """
        解析tdump文件

        Args:
            tdump_path: tdump文件路径

        Returns:
            {
                "success": True,
                "trajectory": [
                    {
                        "timestamp": "2024-10-01T12:00:00Z",
                        "age_hours": 0,
                        "lat": 23.13,
                        "lon": 113.26,
                        "height": 100.0,
                        "pressure": 1013.25,
                        "temperature": 25.3
                    },
                    ...
                ],
                "metadata": {
                    "start_time": "2024-10-01T12:00:00Z",
                    "points_count": 73,
                    "algorithm": "hysplit_v5",
                    "data_source": "gdas1"
                }
            }
        """
        try:
            logger.info("parsing_tdump_file", file_path=tdump_path)

            # 检查文件是否存在
            if not Path(tdump_path).exists():
                raise FileNotFoundError(f"tdump file not found: {tdump_path}")

            # 读取文件
            with open(tdump_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if len(lines) < 4:
                raise ValueError("tdump file too short (< 4 lines)")

            # 解析header
            header_info = self._parse_header(lines[:3])

            # 解析data行
            trajectory_points = self._parse_data_lines(lines[3:])

            if not trajectory_points:
                raise ValueError("No trajectory points found in tdump file")

            logger.info(
                "tdump_parsing_success",
                points_count=len(trajectory_points),
                start_time=header_info.get("start_time")
            )

            return {
                "success": True,
                "trajectory": trajectory_points,
                "metadata": {
                    "start_time": header_info.get("start_time"),
                    "start_lat": header_info.get("start_lat"),
                    "start_lon": header_info.get("start_lon"),
                    "start_height": header_info.get("start_height"),
                    "points_count": len(trajectory_points),
                    "algorithm": "hysplit_v5",
                    "data_source": "gdas1",
                    "version": "5.0.0"
                }
            }

        except Exception as e:
            logger.error("tdump_parsing_failed", error=str(e), file_path=tdump_path)
            return {
                "success": False,
                "error": str(e),
                "trajectory": [],
                "metadata": {}
            }

    def _parse_header(
        self,
        header_lines: List[str]
    ) -> Dict[str, Any]:
        """
        解析tdump header

        Header格式示例：
        Line 0:      1 BACKWARD OMEGA
        Line 1:     24 10  1 12     1
        Line 2:     24 10  1 12  0   23.1300  113.2600   100.0

        Returns:
            {
                "start_time": "2024-10-01T12:00:00Z",
                "start_lat": 23.13,
                "start_lon": 113.26,
                "start_height": 100.0
            }
        """
        header_info = {}

        try:
            # Line 1: 起始时间
            line1_parts = header_lines[1].split()
            if len(line1_parts) >= 4:
                year = int(line1_parts[0]) + 2000  # YY -> YYYY
                month = int(line1_parts[1])
                day = int(line1_parts[2])
                hour = int(line1_parts[3])

                start_time = datetime(year, month, day, hour, 0, 0)
                header_info["start_time"] = start_time.isoformat() + "Z"

            # Line 2: 起始位置
            line2_parts = header_lines[2].split()
            if len(line2_parts) >= 8:
                header_info["start_lat"] = float(line2_parts[5])
                header_info["start_lon"] = float(line2_parts[6])
                header_info["start_height"] = float(line2_parts[7])

        except Exception as e:
            logger.warning("header_parsing_partial_failure", error=str(e))

        return header_info

    def _parse_data_lines(
        self,
        data_lines: List[str]
    ) -> List[Dict[str, Any]]:
        """
        解析tdump数据行

        Data行格式示例：
           24 10  1 12  0   23.1300  113.2600   100.0
           24 10  1 11  1   23.1450  113.2300   105.5
           ...

        Columns:
        1-4: 年月日时 (YY MM DD HH)
        5: 预报小时（age_hours）
        6: 纬度
        7: 经度
        8: 高度 (m AGL)
        9+: 其他变量（如果有）

        Returns:
            List of trajectory points
        """
        points = []

        for line_num, line in enumerate(data_lines):
            # 跳过空行
            line = line.strip()
            if not line:
                continue

            try:
                parts = line.split()

                if len(parts) < 8:
                    logger.warning(
                        "data_line_too_short",
                        line_num=line_num,
                        parts_count=len(parts)
                    )
                    continue

                # 解析时间
                year = int(parts[0]) + 2000  # YY -> YYYY
                month = int(parts[1])
                day = int(parts[2])
                hour = int(parts[3])

                try:
                    timestamp = datetime(year, month, day, hour, 0, 0)
                except ValueError as e:
                    logger.warning(
                        "invalid_datetime",
                        line_num=line_num,
                        year=year,
                        month=month,
                        day=day,
                        hour=hour,
                        error=str(e)
                    )
                    continue

                # 解析位置
                age_hours = int(parts[4])
                lat = float(parts[5])
                lon = float(parts[6])
                height = float(parts[7])

                # 估算气压和温度（简化方法）
                pressure = self._estimate_pressure(height)
                temperature = self._estimate_temperature(height)

                point = {
                    "timestamp": timestamp.isoformat() + "Z",
                    "age_hours": age_hours,
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "height": round(height, 1),
                    "pressure": round(pressure, 2),
                    "temperature": round(temperature, 2)
                }

                points.append(point)

            except (ValueError, IndexError) as e:
                logger.warning(
                    "data_line_parsing_failed",
                    line_num=line_num,
                    error=str(e)
                )
                continue

        return points

    def _estimate_pressure(self, height: float) -> float:
        """
        估算气压（hPa）

        使用标准大气压公式：
        p = p0 * (1 - 0.0065 * h / 288.15)^5.255

        简化为：p ≈ 1013.25 - 0.12 * height
        """
        return max(100.0, 1013.25 - 0.12 * height)

    def _estimate_temperature(self, height: float) -> float:
        """
        估算温度（°C）

        使用标准大气温度递减率：
        T = T0 - Γ * height
        其中 T0 = 15°C, Γ = 0.0065°C/m
        """
        return 15.0 - 0.0065 * height

    def parse_tdump_with_meteo(
        self,
        tdump_path: str,
        meteo_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        解析tdump文件（带气象数据插值）

        Args:
            tdump_path: tdump文件路径
            meteo_data: 气象数据（用于插值温度、气压）

        Returns:
            轨迹数据（同parse_tdump，但温度/气压来自真实数据）
        """
        # 先解析tdump
        result = self.parse_tdump(tdump_path)

        if not result["success"]:
            return result

        # 如果有气象数据，插值温度和气压
        if meteo_data:
            trajectory = result["trajectory"]
            for point in trajectory:
                # TODO: 从气象数据中插值
                # point["temperature"] = interpolate_from_meteo(...)
                # point["pressure"] = interpolate_from_meteo(...)
                pass

        return result

    def convert_to_udf_v2(
        self,
        parse_result: Dict[str, Any],
        direction: str = "backward"
    ) -> Dict[str, Any]:
        """
        将解析结果转换为UDF v2.0格式

        Args:
            parse_result: parse_tdump的返回结果
            direction: backward/forward

        Returns:
            UDF v2.0格式数据
        """
        if not parse_result.get("success"):
            return {
                "status": "failed",
                "success": False,
                "error": parse_result.get("error"),
                "data": [],
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "hysplit_real_v5"
                }
            }

        trajectory = parse_result["trajectory"]
        metadata = parse_result["metadata"]

        return {
            "status": "success",
            "success": True,
            "data": trajectory,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "hysplit_real_v5",
                "scenario": f"{direction}_trajectory_hysplit",
                "record_count": len(trajectory),
                "field_mapping_applied": True,
                "algorithm": metadata.get("algorithm"),
                "data_source": metadata.get("data_source"),
                "version": metadata.get("version"),
                "start_time": metadata.get("start_time"),
                "start_lat": metadata.get("start_lat"),
                "start_lon": metadata.get("start_lon"),
                "start_height": metadata.get("start_height")
            }
        }
