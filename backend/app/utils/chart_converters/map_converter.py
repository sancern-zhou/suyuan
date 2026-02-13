"""
地图数据图表转换器 - UDF v2.0 + Chart v3.1

将空间数据转换为标准地图格式，支持高德地图、热力图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class MapChartConverter:
    """地图数据图表转换器

    专门负责将空间数据转换为各种地图格式
    """

    @staticmethod
    def convert_to_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        chart_type: str = "map",
        **kwargs
    ) -> Dict[str, Any]:
        """将空间数据转换为地图数据

        Args:
            data: 空间数据（UDF格式或字典列表）
            chart_type: 图表类型（map, heatmap）
            **kwargs: 额外参数（map_center, zoom等）

        Returns:
            地图数据（Chart v3.1格式）
        """
        logger.info(
            "map_conversion_start",
            input_type=type(data).__name__,
            chart_type=chart_type,
            record_count=len(data) if isinstance(data, list) else 0
        )

        # 处理输入数据格式
        records = []
        if isinstance(data, dict):
            if "data" in data:
                records = data["data"]
            elif "data_ref" in data:
                return {"error": "数据引用格式需要先加载实际数据", "data_ref": data["data_ref"]}
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        if not records:
            return {"error": "地图数据为空"}

        # 获取配置参数
        map_center = kwargs.get("map_center")
        zoom = kwargs.get("zoom", 12)

        if chart_type == "map":
            return MapChartConverter._generate_map_chart(records, map_center, zoom, **kwargs)
        elif chart_type == "heatmap":
            return MapChartConverter._generate_heatmap_chart(records, map_center, zoom, **kwargs)

        return {"error": f"不支持的地图图表类型: {chart_type}"}

    @staticmethod
    def _generate_map_chart(
        records: List[Dict[str, Any]],
        map_center: Optional[Dict[str, float]],
        zoom: int,
        **kwargs
    ) -> Dict[str, Any]:
        """生成高德地图配置

        Args:
            records: 空间数据记录列表
            map_center: 地图中心点
            zoom: 缩放级别
            **kwargs: 额外参数

        Returns:
            地图数据
        """
        logger.info("map_chart_generation_start", record_count=len(records))

        # 提取marker数据
        markers = []
        lngs = []
        lats = []

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取经纬度
            lng = MapChartConverter._get_field_value(
                record,
                ["longitude", "lng", "经度"]
            )
            lat = MapChartConverter._get_field_value(
                record,
                ["latitude", "lat", "纬度"]
            )

            if lng is None or lat is None:
                continue

            try:
                lng_float = float(lng)
                lat_float = float(lat)

                lngs.append(lng_float)
                lats.append(lat_float)

                # 提取标记信息
                title = MapChartConverter._get_field_value(
                    record,
                    ["title", "name", "station_name", "标记点"]
                ) or "标记点"
                content = MapChartConverter._get_field_value(
                    record,
                    ["content", "description", ""]
                ) or ""
                color = MapChartConverter._get_field_value(
                    record,
                    ["color", "blue"]
                ) or "blue"

                markers.append({
                    "lng": lng_float,
                    "lat": lat_float,
                    "title": title,
                    "content": content,
                    "color": color
                })
            except (ValueError, TypeError):
                continue

        if not markers:
            return {"error": "地图数据中缺少有效的经纬度信息"}

        # 计算地图中心（如果未提供）
        if not map_center:
            map_center = {
                "lng": sum(lngs) / len(lngs),
                "lat": sum(lats) / len(lats)
            }

        # 构建meta信息
        meta = {
            "unit": "站点",
            "data_source": "spatial",
            "marker_count": len(markers),
            "map_center": map_center,
            "zoom": zoom,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "map_chart_generation_complete",
            marker_count=len(markers),
            map_center=map_center
        )

        return {
            "id": "map_chart",
            "type": "map",
            "title": kwargs.get("title", "地图分布"),
            "data": {
                "map_center": map_center,
                "zoom": zoom,
                "layers": [
                    {
                        "type": "marker",
                        "data": markers,
                        "visible": True
                    }
                ]
            },
            "meta": meta
        }

    @staticmethod
    def _generate_heatmap_chart(
        records: List[Dict[str, Any]],
        map_center: Optional[Dict[str, float]],
        zoom: int,
        **kwargs
    ) -> Dict[str, Any]:
        """生成热力图配置

        Args:
            records: 空间数据记录列表
            map_center: 地图中心点
            zoom: 缩放级别
            **kwargs: 额外参数

        Returns:
            热力图数据
        """
        logger.info("heatmap_chart_generation_start", record_count=len(records))

        # 提取热力图数据点
        heatmap_points = []
        lngs = []
        lats = []

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取经纬度
            lng = MapChartConverter._get_field_value(
                record,
                ["longitude", "lng", "经度"]
            )
            lat = MapChartConverter._get_field_value(
                record,
                ["latitude", "lat", "纬度"]
            )

            # 提取值/强度
            value = MapChartConverter._get_field_value(
                record,
                ["value", "intensity", "浓度", 1]
            )

            if lng is None or lat is None:
                continue

            try:
                lng_float = float(lng)
                lat_float = float(lat)
                value_float = float(value)

                lngs.append(lng_float)
                lats.append(lat_float)

                heatmap_points.append({
                    "lng": lng_float,
                    "lat": lat_float,
                    "value": value_float
                })
            except (ValueError, TypeError):
                continue

        if not heatmap_points:
            return {"error": "热力图数据中缺少有效的经纬度和值信息"}

        # 计算地图中心（如果未提供）
        if not map_center:
            map_center = {
                "lng": sum(lngs) / len(lngs),
                "lat": sum(lats) / len(lats)
            }

        # 构建meta信息
        meta = {
            "unit": kwargs.get("unit", "μg/m³"),
            "data_source": "spatial",
            "point_count": len(heatmap_points),
            "map_center": map_center,
            "zoom": zoom,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "heatmap_chart_generation_complete",
            point_count=len(heatmap_points),
            map_center=map_center
        )

        return {
            "id": "heatmap_chart",
            "type": "heatmap",
            "title": kwargs.get("title", "热力分布图"),
            "data": {
                "map_center": map_center,
                "zoom": zoom,
                "layers": [
                    {
                        "type": "heatmap",
                        "data": heatmap_points,
                        "visible": True,
                        "style": {
                            "radius": kwargs.get("radius", 20),
                            "blur": kwargs.get("blur", 15)
                        }
                    }
                ]
            },
            "meta": meta
        }

    @staticmethod
    def _get_field_value(record: Dict[str, Any], field_names: List[str]) -> Any:
        """智能获取字段值

        Args:
            record: 数据记录
            field_names: 候选字段名列表

        Returns:
            字段值
        """
        for field_name in field_names:
            if field_name in record:
                return record[field_name]
        return None
