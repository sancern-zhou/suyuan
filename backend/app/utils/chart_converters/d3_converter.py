"""
3D图表数据转换器 - UDF v2.0 + Chart v3.1

将3D空间数据转换为标准图表格式，支持3D散点图、曲面图、线图、柱状图、体素图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class D3ChartConverter:
    """3D图表数据转换器

    专门负责将3D空间数据转换为各种图表格式
    """

    @staticmethod
    def convert_to_chart(
        data: Union[List[Dict[str, Any]], Dict[str, Any]],
        chart_type: str = "scatter3d",
        **kwargs
    ) -> Dict[str, Any]:
        """将3D数据转换为图表数据

        Args:
            data: 3D数据（UDF格式或字典列表）
            chart_type: 图表类型（scatter3d, surface3d, line3d, bar3d, volume3d）
            **kwargs: 额外参数（title等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "3d_chart_conversion_start",
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
                logger.warning("3d_chart_conversion_data_ref", data_ref=data.get("data_ref"))
                return {"error": "数据引用格式需要先加载实际数据", "data_ref": data["data_ref"]}
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        if not records:
            return {"error": "3D数据为空"}

        # 获取标题
        title = kwargs.get("title", "3D图表")

        if chart_type == "scatter3d":
            return D3ChartConverter._generate_scatter3d(records, title, **kwargs)
        elif chart_type == "surface3d":
            return D3ChartConverter._generate_surface3d(records, title, **kwargs)
        elif chart_type == "line3d":
            return D3ChartConverter._generate_line3d(records, title, **kwargs)
        elif chart_type == "bar3d":
            return D3ChartConverter._generate_bar3d(records, title, **kwargs)
        elif chart_type == "volume3d":
            return D3ChartConverter._generate_volume3d(records, title, **kwargs)

        return {"error": f"不支持的3D图表类型: {chart_type}"}

    @staticmethod
    def _generate_scatter3d(
        records: List[Dict[str, Any]],
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成3D散点图

        Args:
            records: 3D数据记录列表
            title: 图表标题
            **kwargs: 额外参数

        Returns:
            3D散点图数据
        """
        logger.info("scatter3d_chart_generation_start", title=title)

        # 提取xyz坐标和其他属性
        points = []
        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取x、y、z坐标
            x_val = D3ChartConverter._get_field_value(
                record,
                ["x", "longitude", "lng", "经度"]
            )
            y_val = D3ChartConverter._get_field_value(
                record,
                ["y", "latitude", "lat", "纬度"]
            )
            z_val = D3ChartConverter._get_field_value(
                record,
                ["z", "altitude", "height", "高度", "value", "浓度"]
            )

            if x_val is None or y_val is None or z_val is None:
                continue

            try:
                x = float(x_val)
                y = float(y_val)
                z = float(z_val)

                # 提取颜色和大小
                color = D3ChartConverter._get_field_value(
                    record,
                    ["color", "category", "类别"]
                )
                size = D3ChartConverter._get_field_value(
                    record,
                    ["size", "weight", "权重"]
                )

                point = {
                    "x": x,
                    "y": y,
                    "z": z
                }

                if color is not None:
                    point["color"] = str(color)

                if size is not None:
                    try:
                        point["size"] = float(size)
                    except (ValueError, TypeError):
                        pass

                points.append(point)
            except (ValueError, TypeError):
                continue

        if not points:
            return {"error": "3D散点数据中缺少有效的x、y、z坐标"}

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "3d_spatial",
            "point_count": len(points),
            "coordinate_system": "cartesian_3d",
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "scatter3d_chart_generation_complete",
            point_count=len(points)
        )

        return {
            "id": "scatter3d_chart",
            "type": "scatter3d",
            "title": title,
            "data": {
                "points": points,
                "axis_labels": {
                    "x": "X轴",
                    "y": "Y轴",
                    "z": "Z轴"
                }
            },
            "meta": meta
        }

    @staticmethod
    def _generate_surface3d(
        records: List[Dict[str, Any]],
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成3D曲面图

        Args:
            records: 3D数据记录列表
            title: 图表标题
            **kwargs: 额外参数

        Returns:
            3D曲面图数据
        """
        logger.info("surface3d_chart_generation_start", title=title)

        # 提取网格数据
        surface_data = {}

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取x、y、z坐标
            x_val = D3ChartConverter._get_field_value(
                record,
                ["x", "longitude"]
            )
            y_val = D3ChartConverter._get_field_value(
                record,
                ["y", "latitude"]
            )
            z_val = D3ChartConverter._get_field_value(
                record,
                ["z", "value", "浓度"]
            )

            if x_val is None or y_val is None or z_val is None:
                continue

            try:
                x = float(x_val)
                y = float(y_val)
                z = float(z_val)

                # 使用网格键
                grid_x = round(x, 2)
                grid_y = round(y, 2)

                if grid_x not in surface_data:
                    surface_data[grid_x] = {}

                surface_data[grid_x][grid_y] = z
            except (ValueError, TypeError):
                continue

        if not surface_data:
            return {"error": "3D曲面数据中缺少有效的网格数据"}

        # 转换为网格格式
        x_values = sorted(surface_data.keys())
        y_values = sorted(set(y for x in surface_data.values() for y in x.keys()))

        # 构建z值矩阵
        z_matrix = []
        for x in x_values:
            row = []
            for y in y_values:
                z_value = surface_data[x].get(y, None)
                row.append(z_value)
            z_matrix.append(row)

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "3d_spatial",
            "grid_size": f"{len(x_values)}x{len(y_values)}",
            "coordinate_system": "cartesian_3d",
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "surface3d_chart_generation_complete",
            grid_x=len(x_values),
            grid_y=len(y_values)
        )

        return {
            "id": "surface3d_chart",
            "type": "surface3d",
            "title": title,
            "data": {
                "x": x_values,
                "y": y_values,
                "z": z_matrix,
                "axis_labels": {
                    "x": "X轴",
                    "y": "Y轴",
                    "z": "Z轴"
                }
            },
            "meta": meta
        }

    @staticmethod
    def _generate_line3d(
        records: List[Dict[str, Any]],
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成3D线图

        Args:
            records: 3D数据记录列表
            title: 图表标题
            **kwargs: 额外参数

        Returns:
            3D线图数据
        """
        logger.info("line3d_chart_generation_start", title=title)

        # 提取轨迹点
        trajectory_points = []

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取x、y、z坐标
            x_val = D3ChartConverter._get_field_value(
                record,
                ["x", "longitude"]
            )
            y_val = D3ChartConverter._get_field_value(
                record,
                ["y", "latitude"]
            )
            z_val = D3ChartConverter._get_field_value(
                record,
                ["z", "altitude", "高度"]
            )

            if x_val is None or y_val is None or z_val is None:
                continue

            try:
                x = float(x_val)
                y = float(y_val)
                z = float(z_val)

                # 提取顺序
                order = D3ChartConverter._get_field_value(
                    record,
                    ["order", "sequence", "index"]
                ) or len(trajectory_points)

                trajectory_points.append({
                    "x": x,
                    "y": y,
                    "z": z,
                    "order": order
                })
            except (ValueError, TypeError):
                continue

        # 按顺序排序
        trajectory_points.sort(key=lambda p: p["order"])

        # 移除order字段
        trajectory = [{"x": p["x"], "y": p["y"], "z": p["z"]} for p in trajectory_points]

        if len(trajectory) < 2:
            return {"error": "3D线图需要至少2个轨迹点"}

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "3d_spatial",
            "point_count": len(trajectory),
            "coordinate_system": "cartesian_3d",
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "line3d_chart_generation_complete",
            point_count=len(trajectory)
        )

        return {
            "id": "line3d_chart",
            "type": "line3d",
            "title": title,
            "data": {
                "trajectory": trajectory,
                "axis_labels": {
                    "x": "X轴",
                    "y": "Y轴",
                    "z": "Z轴"
                }
            },
            "meta": meta
        }

    @staticmethod
    def _generate_bar3d(
        records: List[Dict[str, Any]],
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成3D柱状图

        Args:
            records: 3D数据记录列表
            title: 图表标题
            **kwargs: 额外参数

        Returns:
            3D柱状图数据
        """
        logger.info("bar3d_chart_generation_start", title=title)

        # 按类别分组数据
        categories = {}

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取类别
            category_x = D3ChartConverter._get_field_value(
                record,
                ["category_x", "x_category", "x分类"]
            )
            category_y = D3ChartConverter._get_field_value(
                record,
                ["category_y", "y_category", "y分类"]
            )
            z_val = D3ChartConverter._get_field_value(
                record,
                ["z", "value", "值"]
            )

            if category_x is None or category_y is None or z_val is None:
                continue

            try:
                z = float(z_val)

                # 创建复合键
                key = f"{category_x}_{category_y}"

                if key not in categories:
                    categories[key] = {
                        "x": str(category_x),
                        "y": str(category_y),
                        "z": z,
                        "count": 1
                    }
                else:
                    # 累加或取平均
                    categories[key]["z"] += z
                    categories[key]["count"] += 1
            except (ValueError, TypeError):
                continue

        # 计算平均值并转换为列表
        bars = []
        for cat_data in categories.values():
            cat_data["z"] /= cat_data["count"]
            bars.append(cat_data)

        if not bars:
            return {"error": "3D柱状图数据格式不正确"}

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "3d_spatial",
            "bar_count": len(bars),
            "coordinate_system": "cartesian_3d",
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "bar3d_chart_generation_complete",
            bar_count=len(bars)
        )

        return {
            "id": "bar3d_chart",
            "type": "bar3d",
            "title": title,
            "data": {
                "bars": bars,
                "axis_labels": {
                    "x": "X轴",
                    "y": "Y轴",
                    "z": "Z轴"
                }
            },
            "meta": meta
        }

    @staticmethod
    def _generate_volume3d(
        records: List[Dict[str, Any]],
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成3D体素图

        Args:
            records: 3D数据记录列表
            title: 图表标题
            **kwargs: 额外参数

        Returns:
            3D体素图数据
        """
        logger.info("volume3d_chart_generation_start", title=title)

        # 提取体数据
        voxels = []
        value_range = {"min": float("inf"), "max": float("-inf")}

        for record in records:
            if not isinstance(record, dict):
                continue

            # 提取x、y、z坐标和值
            x_val = D3ChartConverter._get_field_value(
                record,
                ["x", "longitude"]
            )
            y_val = D3ChartConverter._get_field_value(
                record,
                ["y", "latitude"]
            )
            z_val = D3ChartConverter._get_field_value(
                record,
                ["z", "altitude", "高度"]
            )
            value = D3ChartConverter._get_field_value(
                record,
                ["value", "浓度"]
            )

            if x_val is None or y_val is None or z_val is None or value is None:
                continue

            try:
                x = float(x_val)
                y = float(y_val)
                z = float(z_val)
                v = float(value)

                voxels.append({"x": x, "y": y, "z": z, "value": v})

                # 更新值范围
                if v < value_range["min"]:
                    value_range["min"] = v
                if v > value_range["max"]:
                    value_range["max"] = v
            except (ValueError, TypeError):
                continue

        if not voxels:
            return {"error": "3D体素图数据中缺少有效数据"}

        # 检查值范围合理性
        if value_range["min"] == float("inf") or value_range["max"] == float("-inf"):
            value_range = {"min": 0, "max": 1}

        # 构建meta信息
        meta = {
            "unit": "mixed",
            "data_source": "3d_spatial",
            "voxel_count": len(voxels),
            "value_range": value_range,
            "coordinate_system": "cartesian_3d",
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        logger.info(
            "volume3d_chart_generation_complete",
            voxel_count=len(voxels),
            value_range=value_range
        )

        return {
            "id": "volume3d_chart",
            "type": "volume3d",
            "title": title,
            "data": {
                "voxels": voxels,
                "value_range": value_range,
                "axis_labels": {
                    "x": "X轴",
                    "y": "Y轴",
                    "z": "Z轴"
                }
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
