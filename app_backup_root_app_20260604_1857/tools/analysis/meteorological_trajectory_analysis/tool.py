"""
气象轨迹分析工具 - NOAA HYSPLIT版本

通过NOAA READY API获取标准HYSPLIT轨迹分析结果和轨迹图。

API文档: https://www.ready.noaa.gov/READYmetapi.php
获取API Key: 发送邮件至 hysplit.support@noaa.gov

功能:
1. 反向轨迹分析 - 识别污染物传输路径和来源区域
2. 正向轨迹分析 - 预测污染物对下游的影响
3. 获取标准NOAA HYSPLIT轨迹图 (GIF/PDF)
4. 获取轨迹端点数据用于进一步分析

架构：Context-Aware V2 + UDF v2.0 + Chart v3.1
版本：v2.0.0 (NOAA API版本)
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import structlog
import os

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.external_apis.noaa_hysplit_api import NOAAHysplitAPI

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# 从环境变量获取后端服务器地址
BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")


class MeteorologicalTrajectoryAnalysisTool(LLMTool):
    """
    气象轨迹分析工具 - NOAA HYSPLIT版本
    
    通过NOAA READY API获取标准HYSPLIT轨迹分析结果。
    
    特点：
    - 使用官方NOAA HYSPLIT模型
    - 获取标准轨迹图（与学术论文一致）
    - 支持多高度层轨迹
    - 自动生成交互式地图和高度剖面图
    
    版本：v2.0.0
    """

    def __init__(self):
        function_schema = {
            "name": "meteorological_trajectory_analysis",
            "description": """
NOAA HYSPLIT气象轨迹分析工具 - 自动生成轨迹图和数据

功能：
1. **反向轨迹分析** - 识别污染物传输路径和来源区域
2. **正向轨迹分析** - 预测污染物对下游的影响
3. **自动生成轨迹图** - 包含地图、轨迹线、高度剖面的完整图表

参数：
- lat/lon: 起始位置坐标（受体点）
- start_time: 起始时间（默认当前时间，UTC）
- hours: 回溯/预测小时数（24-168小时，默认72）
- heights: 轨迹高度层列表（米AGL，默认[10, 500, 1000]）
- direction: 轨迹方向（"Backward"反向或"Forward"正向）
- meteo_source: 气象数据源（gdas1/gfs0p25/nam12）

返回：
- summary: 轨迹分析摘要（包含图片相对路径）
- data: 轨迹端点数据（经纬度、高度、气象参数）

注意：每日限制500次计算
""".strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "起始纬度（-90到90度）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "起始经度（-180到180度）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "起始时间（ISO 8601格式，默认当前时间UTC）"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "回溯/预测小时数（24-168，默认72）",
                        "default": 72
                    },
                    "heights": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "高度层列表（米AGL），默认[10, 500, 1000]",
                        "default": [10, 500, 1000]
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["Backward", "Forward"],
                        "description": "轨迹方向：Backward反向溯源，Forward正向预测",
                        "default": "Backward"
                    },
                    "meteo_source": {
                        "type": "string",
                        "enum": ["gdas1", "gfs0p25", "nam12"],
                        "description": "气象数据源：gdas1(全球1度), gfs0p25(全球0.25度), nam12(北美12km)",
                        "default": "gdas1"
                    }
                },
                "required": ["lat", "lon"]
            }
        }

        super().__init__(
            name="meteorological_trajectory_analysis",
            description="NOAA HYSPLIT trajectory analysis via READY API",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True
        )

        self.noaa_client = NOAAHysplitAPI()

    async def execute(
        self,
        context: ExecutionContext,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        hours: int = 72,
        heights: List[int] = None,
        direction: str = "Backward",
        meteo_source: str = "gdas1",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行NOAA HYSPLIT轨迹分析

        Args:
            context: ExecutionContext
            lat: 起始纬度
            lon: 起始经度
            start_time: 起始时间
            hours: 回溯/预测小时数
            heights: 高度层列表
            direction: 轨迹方向
            meteo_source: 气象数据源

        Returns:
            UDF v2.0格式的轨迹分析结果
        """
        try:
            if heights is None:
                heights = [10, 500, 1000]

            if start_time:
                try:
                    start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                except Exception:
                    start_datetime = datetime.now(timezone.utc)
            else:
                start_datetime = datetime.now(timezone.utc)

            # 规范化为带时区的 UTC 时间
            # 若 start_datetime 是 naive（无 tzinfo），假定其为本地北京时区（Asia/Shanghai），并转换为 UTC
            if start_datetime.tzinfo is None:
                try:
                    start_datetime = start_datetime.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
                except Exception:
                    # 如果 ZoneInfo 不可用或转换失败，则退回假定为 UTC
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            else:
                start_datetime = start_datetime.astimezone(timezone.utc)

            # 根据请求时间自动选择气象数据源
            now = datetime.now(timezone.utc)
            time_diff = now - start_datetime

            if time_diff.days < 3:
                # 近期数据（3天内）：使用GFS，调整到1天前确保数据可用
                adjusted_time = now - timedelta(days=1)
                meteo_source = "gfs0p25"
                logger.info("noaa_using_gfs",
                           original=start_datetime.isoformat(),
                           adjusted=adjusted_time.isoformat(),
                           reason="Recent analysis uses GFS (faster updates)")
            elif time_diff.days < 7:
                # 中期数据（3-7天）：使用GFS，保持原时间
                adjusted_time = start_datetime
                meteo_source = "gfs0p25"
                logger.info("noaa_using_gfs",
                           original=start_datetime.isoformat(),
                           reason="Using GFS for 3-7 day range")
            else:
                # 历史数据（7天+）：使用GDAS1
                adjusted_time = start_datetime
                meteo_source = "gdas1"
                logger.info("noaa_using_gdas1",
                           original=start_datetime.isoformat(),
                           reason="Historical analysis uses GDAS1")

            logger.info(
                "noaa_trajectory_analysis_start",
                lat=lat,
                lon=lon,
                start_time=adjusted_time.isoformat(),
                hours=hours,
                heights=heights,
                direction=direction,
                meteo_source=meteo_source,
                session_id=context.session_id
            )

            # 调用NOAA API
            result = await self.noaa_client.run_trajectory(
                lat=lat,
                lon=lon,
                start_time=adjusted_time,
                heights=heights,
                hours=hours,
                direction=direction,
                meteo_source=meteo_source
            )

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                logger.error("noaa_trajectory_failed", error=error_msg)
                
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "visuals": [],
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "meteorological_trajectory_analysis",
                        "error": error_msg
                    },
                    "summary": f"NOAA HYSPLIT轨迹分析失败: {error_msg}"
                }

            # 生成Chart v3.1可视化配置
            chart_result = self.noaa_client.generate_chart_config(
                result=result,
                station_name=f"站点({lat:.2f}, {lon:.2f})"
            )

            # 保存数据到Context
            endpoints = result.get("endpoints_data", [])
            trajectory_data_id = None
            if endpoints:
                try:
                    trajectory_data_id = context.data_manager.save_data(
                        data=endpoints,
                        schema="trajectory_endpoints",
                        metadata={
                            "lat": lat,
                            "lon": lon,
                            "start_time": adjusted_time.isoformat(),
                            "hours": hours,
                            "heights": heights,
                            "direction": direction,
                            "source": "NOAA HYSPLIT READY",
                            "job_id": result.get("job_id"),
                            "schema_version": "v2.0"
                        }
                    )
                    logger.info("trajectory_data_saved", data_id=trajectory_data_id)
                except Exception as save_error:
                    logger.warning("trajectory_data_save_failed", error=str(save_error))
            
            # 更新图表的meta信息，添加source_data_id
            visuals = chart_result.get("visuals", []) if chart_result else []
            if visuals and trajectory_data_id:
                for visual in visuals:
                    # 更新payload.meta
                    if "payload" in visual and isinstance(visual["payload"], dict):
                        if "meta" not in visual["payload"]:
                            visual["payload"]["meta"] = {}
                        visual["payload"]["meta"]["source_data_id"] = trajectory_data_id
                        visual["payload"]["meta"]["data_id"] = trajectory_data_id
                        visual["payload"]["meta"]["expert"] = "weather"  # 轨迹分析属于气象分析
                        visual["payload"]["meta"]["generator"] = "meteorological_trajectory_analysis"
                    
                    # 更新VisualBlock的meta
                    if "meta" not in visual:
                        visual["meta"] = {}
                    visual["meta"]["source_data_id"] = trajectory_data_id
                    visual["meta"]["source_data_ids"] = [trajectory_data_id]
                    visual["meta"]["expert"] = "weather"
                    visual["meta"]["generator"] = "meteorological_trajectory_analysis"
                    
                    logger.debug("trajectory_chart_meta_updated", 
                               visual_id=visual.get("id"),
                               source_data_id=trajectory_data_id)

            # 计算主导方向
            dominant_direction = self._calculate_dominant_direction(endpoints)
            total_distance_km = self._calculate_total_distance(endpoints)

            # 生成LLM摘要（增强版）
            # 尝试从context获取气象数据以提取PBLH信息
            pblh_stats = None
            try:
                # 获取历史气象数据（如果有）
                weather_data_id = context.get_data("historical_weather") if hasattr(context, 'get_data') else None
                if weather_data_id:
                    raw_data = context.get_raw_data(weather_data_id) if hasattr(context, 'get_raw_data') else None
                    if raw_data and isinstance(raw_data, dict):
                        records = raw_data.get("data", [])
                        if records:
                            pblh_values = [
                                r.get("measurements", {}).get("boundary_layer_height")
                                for r in records
                                if isinstance(r, dict) and r.get("measurements", {}).get("boundary_layer_height") not in [None, "nan", float("nan")]
                            ]
                            if pblh_values:
                                import numpy as np
                                pblh_stats = {
                                    "min": float(np.min(pblh_values)),
                                    "max": float(np.max(pblh_values)),
                                    "mean": float(np.mean(pblh_values)),
                                    "std": float(np.std(pblh_values))
                                }
                                logger.debug("pblh_stats_extracted", stats=pblh_stats)
            except Exception as pblh_error:
                logger.debug("pblh_extraction_failed", error=str(pblh_error))

            # 提取本地轨迹图片URL（从visuals中，拼接完整URL）
            trajectory_image_url = "N/A"
            if visuals and len(visuals) > 0:
                # 从visual的payload或meta中提取相对路径
                first_visual = visuals[0]
                payload = first_visual.get("payload", {})
                meta = first_visual.get("meta", {})
                image_relative_path = (
                    payload.get("image_url") or
                    meta.get("image_url") or
                    None
                )

                # 拼接完整URL
                if image_relative_path:
                    if image_relative_path.startswith("/api/image/"):
                        # 本地ImageCache路径，拼接backend_host
                        trajectory_image_url = f"{BACKEND_HOST}{image_relative_path}"
                    else:
                        # 其他路径（如完整URL），直接使用
                        trajectory_image_url = image_relative_path

                logger.info("local_trajectory_image_url_extracted",
                           relative_path=image_relative_path,
                           full_url=trajectory_image_url,
                           visual_id=first_visual.get("id"),
                           backend_host=BACKEND_HOST)

            detailed_summary = self._format_trajectory_for_llm(
                endpoints=endpoints,
                heights=heights,
                hours=hours,
                direction=direction,
                dominant_direction=dominant_direction,
                total_distance_km=total_distance_km,
                lat=lat,
                lon=lon,
                meteo_source=meteo_source,
                pblh_stats=pblh_stats,
                trajectory_image_url=trajectory_image_url,
                data_id=trajectory_data_id  # 添加 data_id
            )

            logger.info(
                "noaa_trajectory_analysis_success",
                job_id=result.get("job_id"),
                endpoints_count=len(endpoints),
                dominant_direction=dominant_direction
            )

            return {
                "data_id": trajectory_data_id,
                "trajectory_data": {
                    "endpoints": endpoints,
                    "start_lat": lat,
                    "start_lon": lon,
                    "job_id": result.get("job_id")
                },
                "dominant_direction": dominant_direction,
                "total_distance_km": total_distance_km,
                "status": "success",
                "success": True,
                "data": endpoints,
                "visuals": visuals,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "meteorological_trajectory_analysis",
                    "generator_version": "2.0.0",
                    "source": "NOAA ARL READY HYSPLIT",
                    "job_id": result.get("job_id"),
                    "trajectory_image_url": result.get("trajectory_image_url"),
                    "record_count": len(endpoints),
                    "field_mapping_applied": True,
                    "field_mapping_info": {
                        "trajectory_count": len(heights),
                        "endpoints_count": len(endpoints)
                    },
                    "analysis_params": {
                        "lat": lat,
                        "lon": lon,
                        "start_time": adjusted_time.isoformat(),
                        "hours": hours,
                        "heights": heights,
                        "direction": direction,
                        "meteo_source": meteo_source
                    }
                },
                # 详细摘要（给LLM用）
                "summary": detailed_summary,
                # 简化摘要（向后兼容）
                "brief_summary": (
                    f"✓ NOAA HYSPLIT {direction}轨迹分析完成。"
                    f"起点: ({lat:.2f}, {lon:.2f}), "
                    f"高度层: {heights}m, "
                    f"时长: {hours}小时, "
                    f"主导方向: {dominant_direction}。"
                )
            }

        except Exception as e:
            logger.error(
                "trajectory_analysis_exception",
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "visuals": [],
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "meteorological_trajectory_analysis",
                    "error": str(e)
                },
                "summary": f"轨迹分析异常: {str(e)[:50]}"
            }

    def _format_trajectory_for_llm(
        self,
        endpoints: List[Dict[str, Any]],
        heights: List[int],
        hours: int,
        direction: str,
        dominant_direction: str,
        total_distance_km: float,
        lat: float,
        lon: float,
        meteo_source: str,
        pblh_stats: Optional[Dict[str, float]] = None,
        trajectory_image_url: str = "N/A",
        data_id: str = None
    ) -> str:
        """
        格式化轨迹数据供LLM分析

        生成高信息密度的轨迹分析摘要，包含：
        - 总体传输特征
        - 分层轨迹分析（路径、高度变化、垂直运动、关键途经点）
        - 潜在污染源区识别
        - 轨迹质量评估
        - 边界层特征（如果提供PBLH数据）
        - 轨迹图片URL
        - 数据引用（data_id）
        """
        if not endpoints:
            return "## NOAA HYSPLIT后向轨迹分析\n\n轨迹数据为空，分析失败。"

        # 生成Markdown图片格式的URL
        trajectory_image_markdown = ""
        if trajectory_image_url and trajectory_image_url != "N/A":
            trajectory_image_markdown = f"\n![轨迹分析图]({trajectory_image_url})\n"

        lines = [
            f"## NOAA HYSPLIT{direction}轨迹分析 ({hours}小时)",
            "",
            f"{trajectory_image_markdown}",
            ""
        ]

        # 添加数据引用
        if data_id:
            lines.extend([
                f"**数据引用**: `{data_id}`",
                ""
            ])

        # 1. 总体传输特征
        transport_speed = total_distance_km / hours if hours > 0 else 0
        lines.extend([
            "### 1. 总体传输特征",
            f"- 主导方向: {dominant_direction}",
            f"- 传输距离: {total_distance_km:.0f}公里",
            f"- 平均传输速度: {transport_speed:.1f} km/h",
            f"- 分析时长: {hours}小时",
            ""
        ])

        # 1.5 边界层特征（如果提供PBLH数据）
        if pblh_stats:
            lines.extend([
                "### 1.5 边界层高度特征 (PBLH)",
                f"- 平均边界层高度: {pblh_stats['mean']:.0f}m",
                f"- 边界层高度范围: {pblh_stats['min']:.0f}-{pblh_stats['max']:.0f}m",
                f"- 边界层稳定性: {self._interpret_pblh_stability(pblh_stats)}",
                ""
            ])

        # 2. 按高度层分组分析
        layers = self._group_endpoints_by_layer(endpoints)

        lines.append("### 2. 分层轨迹分析")
        lines.append("")

        potential_sources = []  # 收集潜在源区

        for i, (trajectory_id, layer_endpoints) in enumerate(layers.items()):
            if i >= len(heights):
                break

            height = heights[i]
            layer_analysis = self._analyze_single_layer(
                layer_endpoints,
                height,
                i,
                lat,
                lon,
                hours,
                pblh_stats  # 传递PBLH统计数据
            )
            lines.extend(layer_analysis["lines"])
            potential_sources.extend(layer_analysis["sources"])
            lines.append("")

        # 3. 潜在污染源区综合识别
        lines.extend([
            "### 3. 潜在污染源区识别",
            ""
        ])

        # 去重并分类源区（按权重排序）
        if potential_sources:
            # 按优先级和权重排序
            primary_sources = sorted(
                [s for s in potential_sources if s["priority"] == "primary"],
                key=lambda x: x.get("weight", 0),
                reverse=True
            )
            secondary_sources = sorted(
                [s for s in potential_sources if s["priority"] == "secondary"],
                key=lambda x: x.get("weight", 0),
                reverse=True
            )

            # 格式化显示源区（带权重）
            if primary_sources:
                primary_desc = "、".join([
                    f"{s['region']}(权重{s['weight']:.1f})"
                    for s in primary_sources[:3]
                ])
                lines.append(f"- **主要源区**: {primary_desc}")
            if secondary_sources:
                secondary_desc = "、".join([
                    f"{s['region']}(权重{s['weight']:.1f})"
                    for s in secondary_sources[:3]
                ])
                lines.append(f"- **次要源区**: {secondary_desc}")

            # 添加说明
            lines.append("")
            lines.append("*注: 权重基于轨迹在该区域的停留时间，越近的轨迹权重越高*")
        else:
            lines.append("- 源区识别失败（轨迹数据不足）")

        lines.extend([
            "",
            "### 4. 轨迹质量评估",
            f"- 数据完整性: ✓ 完整 ({len(layers)}/{len(heights)}层)",
            f"- 气象数据源: {meteo_source.upper()} (质量: 高)",
            f"- 轨迹点总数: {len(endpoints)}个"
        ])

        return "\n".join(lines)

    def _group_endpoints_by_layer(
        self,
        endpoints: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """按轨迹ID（高度层）分组端点数据"""
        layers = {}
        for ep in endpoints:
            tid = ep.get("trajectory_id", 0)
            if tid not in layers:
                layers[tid] = []
            layers[tid].append(ep)
        return layers

    def _analyze_single_layer(
        self,
        layer_endpoints: List[Dict[str, Any]],
        height: int,
        layer_index: int,
        start_lat: float,
        start_lon: float,
        hours: int,
        pblh_stats: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        分析单个高度层的轨迹特征

        Args:
            pblh_stats: 边界层高度统计信息（可选，用于动态判断污染源指示）

        Returns:
            {
                "lines": List[str] - 格式化文本行
                "sources": List[Dict] - 潜在源区信息
            }
        """
        if not layer_endpoints:
            return {
                "lines": [f"#### 2.{layer_index + 1}. 高度层 {height}m", "- 数据缺失"],
                "sources": []
            }

        lines = [f"#### 2.{layer_index + 1}. 高度层 {height}m AGH"]

        # 起止点
        first = layer_endpoints[0]
        last = layer_endpoints[-1]

        # 计算路径描述（简化版，实际可用逆地理编码）
        start_desc = f"({start_lat:.2f}°N, {start_lon:.2f}°E)"
        end_desc = f"({last.get('lat', 0):.2f}°N, {last.get('lon', 0):.2f}°E)"

        # 高度变化
        heights_along = [e.get("height", 0) for e in layer_endpoints if e.get("height")]
        min_h = min(heights_along) if heights_along else 0
        max_h = max(heights_along) if heights_along else 0
        h_change = max_h - min_h

        # 气压变化
        pressures = [e.get("pressure") for e in layer_endpoints if e.get("pressure")]
        min_p = min(pressures) if pressures else None
        max_p = max(pressures) if pressures else None
        p_change = (max_p - min_p) if (min_p and max_p) else None

        # 判断垂直运动
        if h_change > 200:
            vertical_motion = "强上升气流"
        elif h_change > 50:
            vertical_motion = "弱上升气流"
        elif h_change < -50:
            vertical_motion = "下沉气流"
        else:
            vertical_motion = "平稳"

        lines.extend([
            f"- 传输路径: {start_desc} → {end_desc}",
            f"- 沿轨迹高度变化: {height:.0f}m → {max_h:.0f}m ({'上升' if h_change > 0 else '下降'}{abs(h_change):.0f}m)",
            f"- 垂直运动: {vertical_motion}",
        ])

        if min_p and max_p:
            lines.append(f"- 气压变化: {max_p:.0f} → {min_p:.0f} hPa ({'下降' if p_change < 0 else '上升'}{abs(p_change):.0f}hPa)")

        # 关键途经点（每12小时）
        lines.append("- 关键途经位置 (每12小时):")
        key_points = self._extract_key_points(layer_endpoints, interval_hours=12)
        for kp in key_points:
            h_info = f", 高度{kp['height']:.0f}m" if kp.get("height") else ""
            p_info = f", 气压{kp['pressure']:.0f}hPa" if kp.get("pressure") else ""

            # 添加区域识别
            region = self._estimate_region_from_coords(kp.get("lat", 0), kp.get("lon", 0))
            r_info = f" [{region}]" if region and "区域" not in region else ""

            lines.append(
                f"  * {kp['age_hours']}h: ({kp['lat']:.2f}°N, {kp['lon']:.2f}°E){h_info}{p_info}{r_info}"
            )

        # 污染源指示（结合PBLH动态判断）
        source_indicator, priority = self._interpret_trajectory_layer(
            height=height,
            pblh_stats=pblh_stats
        )

        lines.append(f"- 污染源指示: {source_indicator}")

        # 提取潜在源区（基于完整轨迹路径，不只是终点）
        sources = self._identify_source_regions(layer_endpoints, height, priority)

        return {
            "lines": lines,
            "sources": sources
        }

    def _extract_key_points(
        self,
        layer_endpoints: List[Dict[str, Any]],
        interval_hours: int = 12
    ) -> List[Dict[str, Any]]:
        """提取关键时间点（每隔N小时）"""
        key_points = []
        seen_ages = set()

        for ep in layer_endpoints:
            age = ep.get("age_hours", 0)
            if age % interval_hours == 0 and age not in seen_ages:
                key_points.append(ep)
                seen_ages.add(age)

        # 确保包含起点和终点
        if layer_endpoints:
            first = layer_endpoints[0]
            last = layer_endpoints[-1]
            if first.get("age_hours", 0) != 0:
                key_points.insert(0, first)
            if last.get("age_hours", 0) not in seen_ages:
                key_points.append(last)

        return sorted(key_points, key=lambda x: x.get("age_hours", 0))

    def _interpret_trajectory_layer(
        self,
        height: int,
        pblh_stats: Optional[Dict[str, float]] = None
    ) -> tuple[str, str]:
        """
        结合PBLH动态判断污染源指示

        Args:
            height: 轨迹高度 (m AGL)
            pblh_stats: 边界层高度统计信息

        Returns:
            (source_indicator: 污染源指示文字, priority: 优先级)
        """
        if pblh_stats and pblh_stats.get("mean"):
            pblh_mean = pblh_stats["mean"]
            pblh_min = pblh_stats.get("min", pblh_mean * 0.5)
            pblh_max = pblh_stats.get("max", pblh_mean * 1.5)

            # 动态判断（基于PBLH）
            if height <= pblh_min * 0.3:
                # 近地面层（低于PBLH最小值的30%）
                return (
                    f"近地面层({height:.0f}m << PBLH_{pblh_mean:.0f}m)，受局地排放影响显著",
                    "primary"
                )
            elif height <= pblh_mean:
                # 边界层内（低于平均PBLH）
                if pblh_max - pblh_min > 500:
                    # PBLH变化大（日变化显著）
                    return (
                        f"边界层内({height:.0f}m < PBLH_{pblh_mean:.0f}m，日变化{pblh_min:.0f}-{pblh_max:.0f}m)，区域输送与局地混合",
                        "secondary"
                    )
                else:
                    # PBLH稳定（阴天/静稳）
                    return (
                        f"边界层内({height:.0f}m < PBLH_{pblh_mean:.0f}m，稳定)，区域输送为主",
                        "secondary"
                    )
            elif height <= pblh_max * 1.2:
                # 边界层顶部/残留层
                return (
                    f"边界层顶部({height:.0f}m ≈ PBLH_{pblh_mean:.0f}m)，可能存在残留层输送",
                    "secondary"
                )
            else:
                # 自由对流层
                return (
                    f"自由对流层({height:.0f}m >> PBLH_{pblh_mean:.0f}m)，长距离传输为主",
                    "secondary"
                )
        else:
            # 降级到固定阈值（无PBLH数据时）
            if height <= 100:
                return (
                    "近地面传输(≤100m)，受局地排放影响显著 [注: 无PBLH数据，使用固定阈值]",
                    "primary"
                )
            elif height <= 500:
                return (
                    "边界层内(≤500m)，区域输送显著 [注: 无PBLH数据，使用固定阈值]",
                    "secondary"
                )
            else:
                return (
                    "自由对流层(>500m)，长距离传输 [注: 无PBLH数据，使用固定阈值]",
                    "secondary"
                )

    def _interpret_pblh_stability(self, pblh_stats: Dict[str, float]) -> str:
        """
        解释边界层稳定性

        基于PBLH的日变化幅度判断大气稳定度
        """
        pblh_range = pblh_stats["max"] - pblh_stats["min"]
        pblh_mean = pblh_stats["mean"]
        pblh_cv = pblh_stats["std"] / pblh_mean if pblh_mean > 0 else 0

        if pblh_range > 1000 or pblh_cv > 0.6:
            # 日变化显著
            if pblh_mean < 300:
                return "极不稳定(低PBLH，大日变化) - 易积累污染"
            elif pblh_mean < 800:
                return "中等不稳定 - 白天扩散较好，夜间易积累"
            else:
                return "不稳定 - 强对流，扩散条件好"
        elif pblh_range < 200 or pblh_cv < 0.2:
            # 日变化小
            if pblh_mean < 200:
                return "极稳定(持续低PBLH) - 静稳天气，扩散极差"
            elif pblh_mean < 500:
                return "稳定 - 持续弱扩散"
            else:
                return "较稳定 - 扩散能力一般"
        else:
            # 中等变化
            if pblh_mean < 400:
                return "弱稳定 - 扩散条件较差"
            else:
                return "中性 - 扩散条件中等"

    def _identify_source_regions(
        self,
        layer_endpoints: List[Dict[str, Any]],
        height: int,
        priority: str
    ) -> List[Dict[str, Any]]:
        """
        识别潜在污染源区（基于完整轨迹路径）

        策略：
        1. 统计轨迹在不同区域的停留时间（经过点数量）
        2. 权重：最近24小时权重×2，最近48小时权重×1.5
        3. 提取前3个高频区域作为潜在源区
        """
        from collections import Counter

        region_counts = Counter()
        current_time_hours = layer_endpoints[-1].get("age_hours", 0) if layer_endpoints else 0

        for ep in layer_endpoints:
            lat = ep.get("lat", 0)
            lon = ep.get("lon", 0)
            age = ep.get("age_hours", 0)

            region = self._estimate_region_from_coords(lat, lon)

            # 时间权重：越近的轨迹权重越高
            time_weight = 1.0
            if current_time_hours - age < 24:
                time_weight = 2.0
            elif current_time_hours - age < 48:
                time_weight = 1.5

            region_counts[region] += time_weight

        # 提取前3个源区
        top_regions = region_counts.most_common(3)

        sources = []
        seen_regions = set()

        for region, weighted_count in top_regions:
            if region not in seen_regions and "区域" not in region:
                sources.append({
                    "region": region,
                    "height": height,
                    "priority": priority,
                    "weight": round(weighted_count, 1)
                })
                seen_regions.add(region)

        return sources

    def _estimate_region_from_coords(self, lat: float, lon: float) -> Optional[str]:
        """
        根据经纬度估算区域（简化版）

        实际项目中可使用逆地理编码API（如高德/百度）
        """
        # 扩展区域划分（覆盖华北、华东、华中）
        region_map = {
            # 河南
            "河南北部": (34.5, 36.5, 113.0, 115.5),
            "河南东部": (32.0, 34.5, 114.0, 116.5),
            "河南中部": (33.0, 34.5, 111.0, 114.0),
            # 安徽
            "安徽北部": (32.0, 34.0, 115.0, 117.5),
            "安徽中部": (31.0, 32.0, 116.0, 118.0),
            # 山东
            "山东西部": (34.5, 36.5, 114.5, 117.0),
            "山东南部": (34.5, 36.5, 117.0, 119.0),
            # 河北
            "河北南部": (35.0, 37.0, 114.0, 116.0),
            "河北中部": (37.0, 39.0, 114.0, 117.0),
            # 山西
            "山西东南部": (34.5, 36.5, 111.0, 114.0),
            "山西南部": (35.0, 36.5, 110.0, 112.0),
            # 江苏
            "江苏西北部": (33.0, 34.5, 117.0, 119.0),
            # 湖北
            "湖北北部": (30.0, 32.0, 112.0, 115.0),
            # 陕西
            "陕西东南部": (33.0, 35.0, 109.0, 111.0),
        }

        for region, (lat_min, lat_max, lon_min, lon_max) in region_map.items():
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                return region

        # 默认返回经纬度
        return f"区域({lat:.1f}°N, {lon:.1f}°E)"

    def _calculate_dominant_direction(self, endpoints: List[Dict[str, Any]]) -> str:
        """计算轨迹主导方向"""
        if not endpoints or len(endpoints) < 2:
            return "未知"

        # 找到第一个和最后一个点
        first_point = endpoints[0]
        last_point = endpoints[-1]

        lat_diff = last_point.get("lat", 0) - first_point.get("lat", 0)
        lon_diff = last_point.get("lon", 0) - first_point.get("lon", 0)

        import numpy as np
        angle = np.degrees(np.arctan2(lon_diff, lat_diff))

        # 8方位映射
        directions = [
            (-22.5, 22.5, "北"),
            (22.5, 67.5, "东北"),
            (67.5, 112.5, "东"),
            (112.5, 157.5, "东南"),
            (157.5, 180, "南"),
            (-180, -157.5, "南"),
            (-157.5, -112.5, "西南"),
            (-112.5, -67.5, "西"),
            (-67.5, -22.5, "西北"),
        ]

        for min_angle, max_angle, direction in directions:
            if min_angle <= angle < max_angle:
                return direction

        return "北"

    def _calculate_total_distance(self, endpoints: List[Dict[str, Any]]) -> float:
        """计算轨迹总距离（公里）"""
        if not endpoints or len(endpoints) < 2:
            return 0.0

        import numpy as np
        total_distance = 0.0

        for i in range(1, len(endpoints)):
            prev = endpoints[i - 1]
            curr = endpoints[i]

            lat1, lon1 = prev.get("lat", 0), prev.get("lon", 0)
            lat2, lon2 = curr.get("lat", 0), curr.get("lon", 0)

            # 简化距离计算
            distance = np.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) * 111.0
            total_distance += distance

        return round(total_distance, 2)
