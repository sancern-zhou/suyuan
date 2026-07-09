"""
NOAA HYSPLIT READY API Client

通过NOAA READY Web接口获取HYSPLIT轨迹端点数据，
并使用本地matplotlib生成轨迹图（带地图背景和高度剖面）。

轨迹页面: https://www.ready.noaa.gov/HYSPLIT_traj.php

特性:
- 无需API Key，公开访问
- 每日最多500次轨迹计算
- 支持反向/正向轨迹
- 支持多高度层(最多3层)
- 本地matplotlib绘图（不再依赖NOAA图片下载）

架构:
- NOAA HYSPLIT: 计算轨迹端点数据
- matplotlib + cartopy: 本地绘制轨迹图（带地图背景）
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import asyncio
import httpx
import structlog
import re
import os
import base64

logger = structlog.get_logger()

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class NOAAHysplitAPI:
    """
    NOAA HYSPLIT READY API客户端
    
    通过模拟NOAA READY网站的5步表单流程获取轨迹结果。
    无需API Key，公开访问。
    
    流程:
    1. trajtype.pl - 选择轨迹类型
    2. trajasrc.pl - 选择气象数据源
    3. trajsrcm.pl - 输入位置坐标
    4. traj1.pl - 选择气象数据文件
    5. traj2.pl - 设置轨迹参数并运行
    """
    
    BASE_URL = "https://www.ready.noaa.gov"
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    METEO_SOURCES = {
        "gdas1": "GDAS1",
        "gdas0p5": "GDAS0p5",
        "gfs0p25": "GFS0p25",
        "reanalysis": "reanalysis",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """初始化NOAA HYSPLIT API客户端"""
        self.api_key = api_key or os.getenv("NOAA_HYSPLIT_API_KEY")
        self.timeout = httpx.Timeout(180.0, connect=60.0)
        
        self.output_dir = Path("data/noaa_hysplit")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            "noaa_hysplit_api_initialized",
            note="No API key required - NOAA READY is publicly accessible"
        )
    
    async def _request_with_retry(self, client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的HTTP请求"""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                if method.upper() == "GET":
                    return await client.get(url, **kwargs)
                else:
                    return await client.post(url, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "noaa_request_retry",
                        url=url, attempt=attempt + 1, max_retries=self.MAX_RETRIES, error=str(e)
                    )
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        raise last_error
    
    async def run_trajectory(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        heights: List[int] = None,
        hours: int = 72,
        direction: str = "Backward",
        meteo_source: str = "gdas1"
    ) -> Dict[str, Any]:
        """
        运行HYSPLIT轨迹计算
        
        Args:
            lat: 起始纬度
            lon: 起始经度  
            start_time: 起始时间 (UTC) - 注意需要几天延迟才有存档数据
            heights: 高度层列表 (米AGL), 默认[10, 500, 1000], 最多3层
            hours: 回溯/预测小时数 (默认72, 最大315)
            direction: "Backward" 或 "Forward"
            meteo_source: 气象数据源 (gdas1推荐)
            
        Returns:
            包含轨迹图和端点数据的结果字典
        """
        if heights is None:
            heights = [10, 500, 1000]
        heights = heights[:3]  # 最多3层
        
        logger.info(
            "noaa_trajectory_start",
            lat=lat, lon=lon,
            start_time=start_time.isoformat(),
            heights=heights,
            hours=hours,
            direction=direction
        )
        
        try:
            # 添加浏览器User-Agent以模拟正常浏览器请求
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                # Step 1: 初始化会话 (带重试)
                await self._request_with_retry(client, "GET", f"{self.BASE_URL}/hypub-bin/trajtype.pl?runtype=archive")
                
                # Step 2: 选择轨迹类型 (带重试)
                await self._request_with_retry(
                    client, "POST", f"{self.BASE_URL}/hypub-bin/trajasrc.pl",
                    data={"trajtype": "1", "numpts": "1"}
                )
                
                # Step 3: 提交气象数据和位置 (带重试)
                metdata = self.METEO_SOURCES.get(meteo_source.lower(), "GDAS1")
                await self._request_with_retry(
                    client, "POST", f"{self.BASE_URL}/hypub-bin/trajsrcm.pl",
                    data={
                        "metdata": metdata,
                        "Lat": str(abs(lat)),
                        "Latns": "N" if lat >= 0 else "S",
                        "Lon": str(abs(lon)),
                        "Lonew": "E" if lon >= 0 else "W",
                    }
                )
                
                # Step 4: 选择气象文件 (带重试)
                mfile = self._get_meteo_file(start_time, meteo_source)
                resp4 = await self._request_with_retry(
                    client, "POST", f"{self.BASE_URL}/hypub-bin/traj1.pl",
                    data={"mfile": mfile}
                )
                
                if resp4.status_code != 200:
                    return self._error_result("Failed to select meteorology file")
                
                html4 = resp4.text
                if "Total run time" not in html4 and "Direction" not in html4:
                    logger.warning("unexpected_step4_response", preview=html4[:500])
                
                # 找到下一个表单URL
                form_match = re.search(r'<form[^>]+action="([^"]+)"', html4, re.IGNORECASE)
                next_url = form_match.group(1) if form_match else "/hypub-bin/traj2.pl"
                
                # Step 5: 提交轨迹参数并运行
                # 使用正确的NOAA表单参数名称
                dir_val = "Backward" if direction.lower() == "backward" else "Forward"
                
                form_data = {
                    # 坐标 (必须!)
                    "Source lat": str(lat),
                    "Source lon": str(lon),
                    # 方向和时长
                    "direction": dir_val,
                    "duration": str(hours),
                    # 垂直运动方法: 0=model vertical velocity
                    "vertical": "0",
                    # 高度层 (米 AGL)
                    "Source hgt1": str(heights[0]),
                    "Source hgt2": str(heights[1]) if len(heights) > 1 else "0",
                    "Source hgt3": str(heights[2]) if len(heights) > 2 else "0",
                    # 高度单位: 0=meters AGL
                    "Source hunit": "0",
                    # 不使用自动边界层高度
                    "Midlayer height": "No",
                    # 开始时间
                    "Start year": start_time.strftime("%y"),
                    "Start month": start_time.strftime("%m"),
                    "Start day": start_time.strftime("%d"),
                    "Start hour": start_time.strftime("%H"),
                    # 重复轨迹设置
                    "repeatsrc": "0",
                    "ntrajs": "24",
                    # 绘图选项
                    "gis": "0",
                    "Zoom Factor": "70",
                    "projection": "0",
                    "Vertical Unit": "0",
                    "Label Interval": "6",
                    "color": "Yes",
                    "colortype": "No",
                    "pltsrc": "1",
                    "circle": "-1",
                    "county": "arlmap",
                    "psfile": "No",
                    "pdffile": "No",
                    "mplot": "NO",
                }
                
                # Step 5 提交 (带重试)
                resp5 = await self._request_with_retry(
                    client, "POST", f"{self.BASE_URL}{next_url}",
                    data=form_data
                )
                
                html5 = resp5.text
                
                # 提取Job ID
                job_match = re.search(r'jobidno=(\d+)', html5)
                if not job_match:
                    logger.error("job_id_not_found", response_preview=html5[:1000])
                    return self._error_result("Could not find job ID")
                
                job_id = job_match.group(1)
                logger.info("job_submitted", job_id=job_id)
                
                # 等待计算完成
                result_url = f"{self.BASE_URL}/hypub-bin/trajresults.pl?jobidno={job_id}"
                model_complete = False
                endpoints = []  # ✅ 在轮询外定义，用于跨循环访问

                for poll_count in range(40):  # 最多等待2分钟
                    await asyncio.sleep(3)
                    resp = await self._request_with_retry(client, "GET", result_url)
                    text = resp.text

                    # 调试日志：每5次轮询输出一次响应预览
                    if poll_count == 0:
                        # 第一次轮询时保存完整响应用于调试
                        try:
                            with open(f"noaa_response_{job_id}.html", "w", encoding="utf-8") as f:
                                f.write(text)
                            logger.info("noaa_response_saved", job_id=job_id, path=f"noaa_response_{job_id}.html")
                        except Exception as e:
                            logger.warning("noaa_response_save_failed", error=str(e))

                    if poll_count % 5 == 0:
                        # 提取关键内容
                        text_lower = text.lower()
                        logger.info("noaa_polling_status",
                                   job_id=job_id,
                                   poll_count=poll_count,
                                   has_complete=("complete" in text_lower),
                                   has_percent=("percent" in text_lower),
                                   has_jobid=(str(job_id) in text),
                                   response_length=len(text),
                                   response_preview=text[:500] if text else "empty")

                    # ✅ 修复1: 更准确的完成判断（检查多种标记）
                    text_lower = text.lower()
                    has_complete_marker = (
                        "complete hysplit" in text_lower or
                        "percent complete: 100" in text_lower or
                        "100%" in text_lower
                    )

                    # ✅ 修复2: 如果显示完成，尝试获取端点数据来验证
                    if has_complete_marker:
                        # 尝试获取端点数据（如果有端点数据，才认为真正完成）
                        endpoints = await self._get_endpoints(client, job_id)
                        if endpoints:
                            model_complete = True
                            logger.info(
                                "noaa_model_complete",
                                job_id=job_id,
                                verification_method="endpoints_data",
                                endpoints_count=len(endpoints)
                            )
                            break
                        else:
                            # 端点数据还没准备好，继续轮询
                            logger.info(
                                "noaa_complete_but_no_endpoints",
                                job_id=job_id,
                                message="显示完成但端点数据未就绪，继续轮询"
                            )
                            # 继续等待，不要break

                # 【修改】不再尝试下载NOAA图片，直接使用本地绘制
                image_data = None
                local_plot = False

                # ✅ 修复3: 如果在轮询中没获取到端点，最后再尝试一次
                if not endpoints:
                    endpoints = await self._get_endpoints(client, job_id)
                    if endpoints:
                        logger.info("endpoints_fetched_after_polling", job_id=job_id, count=len(endpoints))

                # 对轨迹数据进行抽稀（每1小时保留一个点，保证轨迹圆滑）
                endpoints_downsampled = self._downsample_trajectory(endpoints, interval_hours=1)

                # ✅ 修复4: 优先本地绘制 - 只要有端点数据就尝试绘制
                # 不依赖 model_complete 判断（可能不准确）
                if endpoints_downsampled:
                    logger.info("generating_local_plot", job_id=job_id, endpoints_count=len(endpoints_downsampled))
                    metadata_for_plot = {
                        "lat": lat,
                        "lon": lon,
                        "start_time": start_time.isoformat(),
                        "heights": heights,
                        "hours": hours,
                        "direction": direction,
                        "meteo_source": meteo_source,
                        "job_id": job_id,
                    }
                    image_data = self.generate_local_trajectory_plot(endpoints_downsampled, metadata_for_plot)
                    if image_data:
                        local_plot = True
                        logger.info("local_plot_success", job_id=job_id)
                    else:
                        logger.warning("local_plot_failed", job_id=job_id)
                else:
                    logger.warning("cannot_generate_local_plot", job_id=job_id,
                                   model_complete=model_complete, endpoints_count=len(endpoints_downsampled))

                # ✅ 修复5: 调整成功条件 - 有端点数据且本地绘制成功就算成功
                # model_complete 只是一个参考指标
                success = len(endpoints_downsampled) > 0 and local_plot

                logger.info(
                    "noaa_trajectory_result",
                    job_id=job_id,
                    model_complete=model_complete,
                    local_plot=local_plot,
                    has_image=bool(image_data),
                    endpoints_count=len(endpoints_downsampled),
                    original_endpoints_count=len(endpoints),
                    success_criteria="endpoints_data + local_plot"
                )

                # 如果没有端点数据，返回错误
                if not endpoints_downsampled:
                    error_msg = "NOAA HYSPLIT: No trajectory endpoint data available"
                    logger.error("noaa_trajectory_no_data", job_id=job_id, error=error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "job_id": job_id,
                        "trajectory_image_url": result_url,
                        "trajectory_image_base64": None,
                        "endpoints_data": [],
                        "model_complete": model_complete,
                        "plot_success": False
                    }
                
                return {
                    "success": success,
                    "job_id": job_id,
                    "trajectory_image_url": result_url,  # 保留NOAA结果页面URL
                    "trajectory_image_base64": image_data,  # 本地生成的PNG图片
                    "endpoints_data": endpoints_downsampled,  # 抽稀后的轨迹点
                    "model_complete": model_complete,
                    "plot_success": local_plot,  # 本地绘图是否成功
                    "local_plot": local_plot,
                    "note": "本地matplotlib绘制（带地图背景和高度剖面），轨迹数据已抽稀（每1小时一个点，保证圆滑）" if local_plot else None,
                    "metadata": {
                        "lat": lat,
                        "lon": lon,
                        "start_time": start_time.isoformat(),
                        "heights": heights,
                        "hours": hours,
                        "direction": direction,
                        "meteo_source": meteo_source,
                        "source": "NOAA HYSPLIT 数据计算 + matplotlib 本地绘图",
                        "original_endpoints_count": len(endpoints),
                        "downsampled_endpoints_count": len(endpoints_downsampled),
                        "downsample_interval_hours": 1
                    }
                }
                
        except Exception as e:
            logger.error("noaa_trajectory_failed", error=str(e), exc_info=True)
            return self._error_result(str(e))
    
    def _get_meteo_file(self, start_time: datetime, meteo_source: str) -> str:
        """根据时间选择合适的气象数据文件"""
        # 对于GFS0p25，使用日期格式: 20251208_gfs0p25
        if meteo_source.lower() == "gfs0p25":
            return start_time.strftime("%Y%m%d") + "_gfs0p25"
        
        # 对于GDAS1，使用周文件格式: gdas1.nov25.w1
        month_abbr = start_time.strftime("%b").lower()
        year_2digit = start_time.strftime("%y")
        week_of_month = (start_time.day - 1) // 7 + 1
        
        return f"gdas1.{month_abbr}{year_2digit}.w{week_of_month}"

    async def _get_endpoints(
        self,
        client: httpx.AsyncClient,
        job_id: str
    ) -> List[Dict[str, Any]]:
        """获取轨迹端点数据

        添加重试机制：有时页面显示完成但tdump文件还在写入中
        """
        try:
            # 尝试多个URL格式
            urls = [
                f"{self.BASE_URL}/hypubout/tdump.{job_id}.txt",
                f"{self.BASE_URL}/hypub-bin/trajendpts.pl?jobidno={job_id}",
            ]

            for url in urls:
                # 最多重试3次，每次等待2秒
                for attempt in range(3):
                    resp = await client.get(url)
                    if resp.status_code == 200 and len(resp.text) > 100:
                        endpoints = self._parse_endpoints(resp.text)
                        if endpoints:
                            logger.info("endpoints_fetched", url=url, count=len(endpoints), attempt=attempt)
                            return endpoints
                        elif attempt < 2:
                            # 解析失败但文件存在，可能是文件还在写入
                            logger.info("endpoints_retry_empty", url=url, attempt=attempt, file_size=len(resp.text))
                            await asyncio.sleep(2)
                    else:
                        break

            return []
        except Exception as e:
            logger.error("endpoints_error", error=str(e))
            return []
    
    def _parse_endpoints(self, text: str) -> List[Dict[str, Any]]:
        """解析HYSPLIT端点数据"""
        endpoints = []

        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("<"):
                continue

            parts = line.split()
            if len(parts) >= 12:
                try:
                    year = int(parts[2])
                    if year < 100:
                        year += 2000

                    endpoints.append({
                        "trajectory_id": int(parts[0]),
                        "year": year,
                        "month": int(parts[3]),
                        "day": int(parts[4]),
                        "hour": int(parts[5]),
                        "age_hours": float(parts[8]),
                        "lat": float(parts[9]),
                        "lon": float(parts[10]),
                        "height": float(parts[11]),
                        "pressure": float(parts[12]) if len(parts) > 12 else None,
                        "timestamp": f"{year}-{int(parts[3]):02d}-{int(parts[4]):02d}T{int(parts[5]):02d}:00:00Z"
                    })
                except (ValueError, IndexError):
                    continue

        return endpoints

    def _downsample_trajectory(
        self,
        endpoints: List[Dict[str, Any]],
        interval_hours: int = 12
    ) -> List[Dict[str, Any]]:
        """
        对轨迹数据进行时间间隔抽稀，减少数据量

        Args:
            endpoints: 完整的轨迹端点数据
            interval_hours: 时间间隔（小时），默认12小时保留一个点

        Returns:
            抽稀后的轨迹点列表
        """
        if not endpoints:
            return []

        # 按轨迹ID分组
        trajectories_by_id = {}
        for ep in endpoints:
            traj_id = ep.get("trajectory_id", 1)
            if traj_id not in trajectories_by_id:
                trajectories_by_id[traj_id] = []
            trajectories_by_id[traj_id].append(ep)

        # 对每条轨迹进行抽稀
        key_points = []
        for traj_id, points in trajectories_by_id.items():
            # 按age_hours排序（确保时间顺序）
            points_sorted = sorted(points, key=lambda p: abs(p.get("age_hours", 0)))

            # 保留起点（age_hours=0）
            if points_sorted:
                key_points.append(points_sorted[0])

            # 按时间间隔抽稀
            for point in points_sorted[1:]:
                age = abs(point.get("age_hours", 0))
                # 保留能被interval_hours整除的点
                if age % interval_hours == 0:
                    key_points.append(point)

        logger.info(
            "trajectory_downsampled",
            full_count=len(endpoints),
            downsampled_count=len(key_points),
            reduction_ratio=f"{(1 - len(key_points)/len(endpoints))*100:.1f}%",
            interval_hours=interval_hours
        )

        return key_points
    
    def _error_result(self, error: str) -> Dict[str, Any]:
        """生成错误结果"""
        return {
            "success": False,
            "error": error,
            "job_id": None,
            "trajectory_image_url": None,
            "trajectory_image_base64": None,
            "endpoints_data": []
        }
    
    def _save_image_to_cache(self, base64_data: str, chart_id: str) -> str:
        """将base64图片保存到缓存，返回image_id"""
        from app.services.image_cache import get_image_cache
        cache = get_image_cache()
        return cache.save(base64_data, chart_id)

    def _get_image_url(self, image_id: str) -> str:
        """获取图片访问URL"""
        return f"/api/image/{image_id}"

    def generate_chart_config(
        self,
        result: Dict[str, Any],
        station_name: str = "Unknown"
    ) -> Dict[str, Any]:
        """生成Chart v3.1格式的可视化配置"""
        if not result.get("success"):
            return None

        metadata = result.get("metadata", {})
        endpoints = result.get("endpoints_data", [])
        image_base64 = result.get("trajectory_image_base64")

        visuals = []

        # 公共meta信息
        job_id = result.get("job_id")
        direction = metadata.get("direction", "Backward")
        scenario = "trajectory_analysis"

        # 使用本地matplotlib生成的轨迹图（PNG格式）
        # 包含：地图背景（海岸线、国界）+ 轨迹线 + 高度剖面
        if image_base64:
            # 所有图片都是本地生成的PNG格式
            is_png = result.get("local_plot", True)  # 默认True，因为不再使用NOAA图片

            # 生成唯一的图表ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            chart_id = f"trajectory_local_{timestamp}_{job_id}" if job_id else f"trajectory_local_{timestamp}"

            # 保存图片到缓存，返回字典
            image_info = self._save_image_to_cache(image_base64, chart_id)
            image_id = image_info["image_id"]  # 提取image_id字符串
            image_url = image_info["url"]  # 提取URL字符串

            logger.info("trajectory_image_saved_to_cache", image_id=image_id, chart_id=chart_id, image_url=image_url)

            # 确定MIME类型（现在总是PNG）
            mime_type = "image/png"

            visuals.append({
                "id": image_id,  # 使用image_id作为visual的id
                "type": "image",
                "schema": "chart_config",
                "payload": {
                    "id": image_id,
                    "type": "image",
                    "title": f"HYSPLIT {direction}轨迹分析 - {station_name}",
                    "data": f"[IMAGE:{image_id}]",  # Placeholder
                    "image_id": image_id,  # 图片ID，供weather_executor使用
                    "image_url": image_url,  # 图片URL，供LLM生成Markdown链接
                    "markdown_image": f"![HYSPLIT {direction}轨迹分析]({image_url})",  # 预生成的Markdown格式
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "noaa_hysplit_local_plot",
                        "scenario": scenario,
                        "layout_hint": "wide",
                        "original_data_ids": [f"job_{job_id}"] if job_id else [],
                        "source": "NOAA HYSPLIT计算 + matplotlib本地绘制（地图+剖面）"
                    }
                },
                # UDF v2.0 VisualBlock外层meta
                "meta": {
                    "schema_version": "v2.0",
                    "generator": "noaa_hysplit_local_plot",
                    "scenario": scenario,
                    "source_data_ids": [f"job_{job_id}"] if job_id else [],
                    "image_id": image_id,
                    "image_url": image_url
                }
            })

        # 端点数据保留用于数据分析
        trajectories_by_id = {}
        if endpoints:
            for ep in endpoints:
                traj_id = ep.get("trajectory_id", 1)
                if traj_id not in trajectories_by_id:
                    trajectories_by_id[traj_id] = []
                trajectories_by_id[traj_id].append(ep)

        return {
            "status": "success",
            "success": True,
            "data": endpoints,
            "visuals": visuals,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "noaa_hysplit_local_plot",
                "source": "NOAA HYSPLIT计算 + matplotlib本地绘制",
                "job_id": result.get("job_id"),
                "trajectory_image_url": result.get("trajectory_image_url"),
                **metadata
            }
        }

    @staticmethod
    def _format_local_plot_labels(
        direction: str,
        start_time: Any,
        meteo_source: str,
        job_id: Optional[str],
        lat: float,
        lon: float,
        heights: List[int],
        hours: int,
    ) -> Dict[str, Any]:
        """生成本地轨迹图中文标签。"""
        direction_name = "后向" if str(direction).lower() == "backward" else "前向"
        try:
            if isinstance(start_time, str):
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            else:
                start_dt = start_time
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            beijing_dt = start_dt.astimezone(BEIJING_TZ)
            time_label = beijing_dt.strftime("%Y年%m月%d日 %H:%M 北京时间")
            meteo_time = beijing_dt.strftime("%Y-%m-%d %H:%M 北京时间")
        except Exception:
            time_label = str(start_time)
            meteo_time = str(start_time)

        event_label = "终止时间" if direction_name == "后向" else "起始时间"
        heights_str = ", ".join(map(str, heights))
        job_start = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S 北京时间")
        info_lines = [
            f"任务编号: {job_id or 'N/A'}        生成时间: {job_start}",
            f"源点1: 纬度 {lat:.6f} 经度 {lon:.6f} 高度: {heights_str} m AGL",
            f"轨迹方向: {direction_name}        时长: {hours} 小时",
            "垂直运动: 模式垂直速度",
            f"气象资料: {meteo_time} - {str(meteo_source).upper()}",
        ]
        return {
            "direction_name": direction_name,
            "title_lines": [
                "NOAA HYSPLIT 模型",
                f"{hours}小时{direction_name}轨迹，{event_label}：{time_label}",
                f"{str(meteo_source).upper()} 气象数据",
            ],
            "source_label": f"源点 ★  {lat:.2f}°N {lon:.2f}°E",
            "height_label": "高度 (m AGL)",
            "info_text": "\n".join(info_lines),
        }

    @staticmethod
    def _resolve_height_axis(
        plotted_heights: List[float],
        configured_heights: List[int],
    ) -> tuple[float, float, List[int]]:
        """计算高度剖面轴范围，给上下边界留白避免线和标记贴边。"""
        import math

        max_height = max(max(plotted_heights or [0]), max(configured_heights or [0]))
        tick_top = max(3500, int(math.ceil(max_height / 500.0) * 500))
        lower = -tick_top * 0.08
        upper = tick_top * 1.08
        ticks = list(range(500, tick_top + 1, 500))
        return lower, upper, ticks
    
    def generate_local_trajectory_plot(
        self,
        endpoints: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        使用matplotlib+cartopy本地生成HYSPLIT轨迹图（主要绘图方法）

        生成内容包括：
        1. 地图背景（海岸线、国界、省界）
        2. 多层轨迹线（不同高度层用不同颜色）
        3. 高度时序剖面图

        Args:
            endpoints: 轨迹端点数据
            metadata: 轨迹元数据（lat, lon, heights, direction等）
            output_path: 输出文件路径（可选，默认None不保存文件）

        Returns:
            Base64编码的PNG图片数据，或None（绘图失败时）
        """
        if not endpoints:
            return None
        
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.gridspec import GridSpec
            from io import BytesIO
            try:
                from app.utils.font_utils import configure_chinese_font
                configure_chinese_font()
            except Exception as font_error:
                logger.debug("configure_chinese_font_failed", error=str(font_error))

            logger.info("local_trajectory_plot_start", endpoints_count=len(endpoints))

            # 尝试导入cartopy用于地图背景
            use_cartopy = False
            try:
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                use_cartopy = True
                logger.info("cartopy_available_for_plot")
            except ImportError:
                logger.warning("cartopy_not_available", note="使用简单散点图，无地图背景")

            # 按轨迹ID分组
            trajectories = {}
            for ep in endpoints:
                traj_id = ep.get("trajectory_id", 1)
                if traj_id not in trajectories:
                    trajectories[traj_id] = []
                trajectories[traj_id].append(ep)

            # 自适应计算地图范围
            all_lons = [p["lon"] for points in trajectories.values() for p in points]
            all_lats = [p["lat"] for points in trajectories.values() for p in points]

            # 添加起点坐标（确保起点在视野内）
            start_lat = metadata.get("lat", 0)
            start_lon = metadata.get("lon", 0)
            all_lons.append(start_lon)
            all_lats.append(start_lat)

            lon_min, lon_max = min(all_lons), max(all_lons)
            lat_min, lat_max = min(all_lats), max(all_lats)

            # 添加15%边距（确保轨迹不贴边）
            margin = 0.15
            lon_range = max(lon_max - lon_min, 1.0)  # 最小1度范围
            lat_range = max(lat_max - lat_min, 1.0)

            lon_min_padded = lon_min - lon_range * margin
            lon_max_padded = lon_max + lon_range * margin
            lat_min_padded = lat_min - lat_range * margin
            lat_max_padded = lat_max + lat_range * margin

            # 使用自然地理范围，不强制调整比例（让Cartopy自适应GridSpec宽度）
            extent = [lon_min_padded, lon_max_padded, lat_min_padded, lat_max_padded]

            logger.info("adaptive_map_extent_calculated",
                       lon_range=f"{lon_min_padded:.2f} to {lon_max_padded:.2f}",
                       lat_range=f"{lat_min_padded:.2f} to {lat_max_padded:.2f}",
                       aspect_ratio=f"{(lon_max_padded - lon_min_padded) / (lat_max_padded - lat_min_padded):.2f}")

            direction = metadata.get("direction", "Backward")
            start_time_str = metadata.get("start_time", "")
            lat = metadata.get("lat", 0)
            lon = metadata.get("lon", 0)
            heights_list = metadata.get("heights", [500, 1500, 2500])
            hours = metadata.get("hours", 72)
            meteo_source = metadata.get("meteo_source", "gdas1")
            job_id = metadata.get("job_id")

            labels = self._format_local_plot_labels(
                direction=direction,
                start_time=start_time_str,
                meteo_source=meteo_source,
                job_id=job_id,
                lat=lat,
                lon=lon,
                heights=heights_list,
                hours=hours,
            )

            # NOAA官方图接近588x730，使用相同竖版比例，三段结构：地图、剖面、信息栏。
            fig = plt.figure(figsize=(5.88, 7.30), facecolor="white")
            gs = GridSpec(
                3,
                1,
                height_ratios=[5.05, 1.2, 1.45],
                hspace=0.08,
                left=0.04,
                right=0.96,
                top=0.90,
                bottom=0.04,
            )

            ax_height = fig.add_subplot(gs[1])
            ax_info = fig.add_subplot(gs[2])

            if use_cartopy:
                # 创建 cartopy map axes
                ax_map = fig.add_subplot(gs[0], projection=ccrs.PlateCarree())
                ax_map.set_extent(extent, crs=ccrs.PlateCarree())
                # 关键：设置aspect为auto，让地图适应GridSpec宽度（不强制地理比例）
                ax_map.set_aspect('auto', adjustable='box')

                # NOAA READY图以白底和浅蓝地理线为主，不使用填色底图。
                ax_map.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor="#6aa6de")
                ax_map.add_feature(cfeature.BORDERS, linewidth=0.45, edgecolor="#6aa6de")
                ax_map.add_feature(cfeature.LAKES, facecolor="none", edgecolor="#6aa6de", linewidth=0.35)

                # 添加省界（如果可用）
                try:
                    ax_map.add_feature(cfeature.STATES, linewidth=0.25, edgecolor="#8bb9e6")
                except Exception:
                    pass

                ax_map.gridlines(
                    draw_labels=False,
                    linewidth=0.55,
                    color="#6aa6de",
                    alpha=0.8,
                    linestyle="--",
                )
            else:
                # 非cartopy模式：创建普通map axes
                ax_map = fig.add_subplot(gs[0])
                ax_map.set_xlim(extent[0], extent[1])
                ax_map.set_ylim(extent[2], extent[3])
                ax_map.grid(True, linestyle="--", color="#6aa6de", alpha=0.8, linewidth=0.55)

            import math

            def _nice_ticks(min_value: float, max_value: float, step: int = 5) -> List[int]:
                start = math.ceil(min_value / step) * step
                end = math.floor(max_value / step) * step
                ticks = list(range(int(start), int(end) + 1, step))
                if not ticks:
                    ticks = [round((min_value + max_value) / 2)]
                return ticks

            lon_ticks = _nice_ticks(extent[0], extent[1])
            lat_ticks = _nice_ticks(extent[2], extent[3])
            if use_cartopy:
                ax_map.set_xticks(lon_ticks, crs=ccrs.PlateCarree())
                ax_map.set_yticks(lat_ticks, crs=ccrs.PlateCarree())
            else:
                ax_map.set_xticks(lon_ticks)
                ax_map.set_yticks(lat_ticks)

            ax_map.tick_params(axis="y", labelsize=9, colors="#5b9bd5", length=0)
            ax_map.tick_params(axis="x", labelsize=9, colors="#5b9bd5", length=0, pad=-16)
            for tick_label in ax_map.get_xticklabels():
                tick_label.set_verticalalignment("bottom")
                tick_label.set_bbox(
                    {"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 0.2}
                )
            ax_map.set_ylabel(labels["source_label"], fontsize=11, color="black")
            for spine in ax_map.spines.values():
                spine.set_visible(True)
                spine.set_color("black")
                spine.set_linewidth(1.2)

            colors = ["red", "blue", "#00cc2a"]
            markers = ["^", "s", "o"]
            
            # 绘制轨迹
            for i, (traj_id, points) in enumerate(sorted(trajectories.items())):
                points = sorted(points, key=lambda p: abs(p.get("age_hours", 0)))
                lats = [p["lat"] for p in points]
                lons = [p["lon"] for p in points]
                heights = [p["height"] for p in points]
                ages = [abs(p.get("age_hours", 0)) for p in points]
                
                color = colors[i % len(colors)]
                marker = markers[i % len(markers)]
                
                # 地图轨迹
                if use_cartopy:
                    ax_map.plot(
                        lons,
                        lats,
                        "-",
                        color=color,
                        linewidth=1.8,
                        transform=ccrs.PlateCarree(),
                    )
                    for point_lon, point_lat, age in zip(lons, lats, ages):
                        if age % 6 == 0:
                            ax_map.plot(
                                point_lon,
                                point_lat,
                                marker,
                                color=color,
                                markersize=4.5,
                                markeredgewidth=0,
                                transform=ccrs.PlateCarree(),
                            )
                    # 起点标记
                    ax_map.plot(
                        lons[0],
                        lats[0],
                        "*",
                        color="black",
                        markersize=12,
                        transform=ccrs.PlateCarree(),
                    )
                else:
                    ax_map.plot(lons, lats, "-", color=color, linewidth=1.8)
                    for point_lon, point_lat, age in zip(lons, lats, ages):
                        if age % 6 == 0:
                            ax_map.plot(point_lon, point_lat, marker, color=color, markersize=4.5)
                    ax_map.plot(lons[0], lats[0], "*", color="black", markersize=12)
                
                # 高度剖面
                ax_height.plot(ages, heights, "-", color=color, linewidth=1.6)
                ax_height.plot(ages, heights, marker, color=color, markersize=4, markeredgewidth=0)
            
            # 高度剖面设置
            max_age = max(abs(p.get("age_hours", 0)) for p in endpoints)
            ax_height.set_xlim(max_age, 0)
            ax_height.set_ylabel(labels["height_label"], fontsize=11)
            ax_height.yaxis.set_label_position("left")
            ax_height.yaxis.tick_right()
            ax_height.tick_params(axis="x", labelsize=9, colors="black", length=0)
            ax_height.tick_params(axis="y", labelsize=9, colors="black", length=0, pad=-38)
            ax_height.grid(True, axis="y", linestyle=(0, (6, 6)), color="#9f9f9f", linewidth=0.9)
            ax_height.grid(False, axis="x")
            ax_height.set_xticks(list(range(int(max_age), -1, -6)))
            for spine in ax_height.spines.values():
                spine.set_visible(True)
                spine.set_color("black")
                spine.set_linewidth(1.2)

            all_heights = [p["height"] for points in trajectories.values() for p in points]
            y_lower, y_upper, height_ticks = self._resolve_height_axis(all_heights, heights_list)
            ax_height.set_ylim(y_lower, y_upper)
            ax_height.set_yticks(height_ticks)

            fig.suptitle(
                "\n".join(labels["title_lines"]),
                fontsize=13,
                fontweight="normal",
                y=0.985,
                linespacing=1.05,
            )

            ax_info.set_facecolor("white")
            ax_info.set_xticks([])
            ax_info.set_yticks([])
            for spine in ax_info.spines.values():
                spine.set_visible(True)
                spine.set_color("black")
                spine.set_linewidth(1.2)

            ax_info.text(
                0.05,
                0.88,
                labels["info_text"],
                transform=ax_info.transAxes,
                fontsize=7.6,
                va="top",
                ha="left",
                color="black",
            )

            # 保存到内存（不使用bbox_inches='tight'，确保上下图宽度一致）
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, facecolor='white', pad_inches=0.0)
            plt.close(fig)

            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            logger.info("local_trajectory_plot_success",
                       size_kb=len(image_base64) / 1024,
                       use_cartopy=use_cartopy)

            # 可选：保存到文件
            if output_path:
                buffer.seek(0)
                with open(output_path, 'wb') as f:
                    f.write(buffer.read())
                logger.info("local_plot_saved", path=output_path)

            return image_base64

        except Exception as e:
            logger.error("local_trajectory_plot_failed", error=str(e), exc_info=True)
            return None
