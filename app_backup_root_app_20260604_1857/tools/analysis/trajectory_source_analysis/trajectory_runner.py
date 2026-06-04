"""
NOAA HYSPLIT 批量轨迹运行器

负责批量调用NOAA HYSPLIT API运行多条轨迹，并合并端点数据。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import structlog

from app.external_apis.noaa_hysplit_api import NOAAHysplitAPI

logger = structlog.get_logger()


class TrajectoryRunner:
    """
    批量轨迹运行器
    
    特性：
    - 支持多时间点、多高度层轨迹
    - 并发控制（避免NOAA API限流）
    - 自动重试失败的轨迹
    """
    
    def __init__(self, max_concurrent: int = 3):
        """
        初始化轨迹运行器
        
        Args:
            max_concurrent: 最大并发数（NOAA建议不超过5）
        """
        self.noaa_client = NOAAHysplitAPI()
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    def generate_trajectory_configs(
        self,
        lat: float,
        lon: float,
        mode: str,
        days: int = 2,
        heights: List[int] = None,
        time_interval_hours: int = 6
    ) -> List[Dict[str, Any]]:
        """
        生成多条轨迹的配置
        
        Args:
            lat: 分析点纬度
            lon: 分析点经度
            mode: 分析模式 (backward/forward)
            days: 分析天数
            heights: 高度层列表
            time_interval_hours: 轨迹起始时间间隔（小时）
        
        Returns:
            轨迹配置列表
        """
        if heights is None:
            heights = [100, 500, 1000]
        
        configs = []
        total_hours = days * 24
        
        if mode == "backward":
            # 后向轨迹：从不同时间点回溯
            # 每隔time_interval_hours小时启动一条轨迹
            num_trajectories = total_hours // time_interval_hours
            
            for i in range(num_trajectories):
                offset_hours = i * time_interval_hours
                # NOAA需要UTC时间，且需要几天的数据延迟
                # 使用1天前的时间确保数据可用
                start_time = datetime.utcnow() - timedelta(days=1, hours=offset_hours)
                
                configs.append({
                    "lat": lat,
                    "lon": lon,
                    "start_time": start_time,
                    "heights": heights,
                    "hours": total_hours,
                    "direction": "Backward",
                    "meteo_source": "gfs0p25"
                })
        else:
            # 前向轨迹：从当前时间预测
            # 只需要一个起始时间，但多个高度层
            start_time = datetime.utcnow() - timedelta(days=1)
            
            configs.append({
                "lat": lat,
                "lon": lon,
                "start_time": start_time,
                "heights": heights,
                "hours": total_hours,
                "direction": "Forward",
                "meteo_source": "gfs0p25"
            })
        
        logger.info(
            "trajectory_configs_generated",
            mode=mode,
            days=days,
            num_configs=len(configs),
            heights=heights
        )
        
        return configs
    
    async def run_single_trajectory(
        self,
        config: Dict[str, Any],
        config_index: int
    ) -> Dict[str, Any]:
        """
        运行单条轨迹（带并发控制）
        
        Args:
            config: 轨迹配置
            config_index: 配置索引（用于日志）
        
        Returns:
            轨迹结果
        """
        async with self.semaphore:
            try:
                logger.info(
                    "trajectory_start",
                    index=config_index,
                    start_time=config["start_time"].isoformat(),
                    direction=config["direction"]
                )
                
                result = await self.noaa_client.run_trajectory(
                    lat=config["lat"],
                    lon=config["lon"],
                    start_time=config["start_time"],
                    heights=config["heights"],
                    hours=config["hours"],
                    direction=config["direction"],
                    meteo_source=config["meteo_source"]
                )
                
                if result.get("success"):
                    endpoints_count = len(result.get("endpoints_data", []))
                    logger.info(
                        "trajectory_success",
                        index=config_index,
                        job_id=result.get("job_id"),
                        endpoints_count=endpoints_count
                    )
                else:
                    logger.warning(
                        "trajectory_failed",
                        index=config_index,
                        error=result.get("error")
                    )
                
                return {
                    "config_index": config_index,
                    "config": config,
                    "result": result
                }
                
            except Exception as e:
                logger.error(
                    "trajectory_exception",
                    index=config_index,
                    error=str(e)
                )
                return {
                    "config_index": config_index,
                    "config": config,
                    "result": {"success": False, "error": str(e), "endpoints_data": []}
                }
    
    async def run_batch_trajectories(
        self,
        configs: List[Dict[str, Any]],
        retry_failed: bool = True
    ) -> Dict[str, Any]:
        """
        批量运行轨迹
        
        Args:
            configs: 轨迹配置列表
            retry_failed: 是否重试失败的轨迹
        
        Returns:
            批量结果，包含所有端点数据
        """
        logger.info(
            "batch_trajectories_start",
            total_configs=len(configs),
            max_concurrent=self.max_concurrent
        )
        
        # 并发运行所有轨迹
        tasks = [
            self.run_single_trajectory(config, i)
            for i, config in enumerate(configs)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        all_endpoints = []
        successful_jobs = []
        failed_jobs = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_jobs.append({"index": i, "error": str(result)})
                continue
            
            if result["result"].get("success"):
                endpoints = result["result"].get("endpoints_data", [])
                # 添加轨迹批次标识
                for ep in endpoints:
                    ep["batch_index"] = result["config_index"]
                all_endpoints.extend(endpoints)
                successful_jobs.append({
                    "index": result["config_index"],
                    "job_id": result["result"].get("job_id"),
                    "endpoints_count": len(endpoints)
                })
            else:
                failed_jobs.append({
                    "index": result["config_index"],
                    "error": result["result"].get("error")
                })
        
        # 重试失败的轨迹（可选）
        if retry_failed and failed_jobs:
            logger.info(
                "retrying_failed_trajectories",
                failed_count=len(failed_jobs)
            )
            
            retry_configs = [configs[f["index"]] for f in failed_jobs]
            retry_tasks = [
                self.run_single_trajectory(config, f["index"])
                for config, f in zip(retry_configs, failed_jobs)
            ]
            
            retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
            
            for result in retry_results:
                if isinstance(result, Exception):
                    continue
                if result["result"].get("success"):
                    endpoints = result["result"].get("endpoints_data", [])
                    for ep in endpoints:
                        ep["batch_index"] = result["config_index"]
                    all_endpoints.extend(endpoints)
                    successful_jobs.append({
                        "index": result["config_index"],
                        "job_id": result["result"].get("job_id"),
                        "endpoints_count": len(endpoints),
                        "retry": True
                    })
        
        logger.info(
            "batch_trajectories_complete",
            successful=len(successful_jobs),
            failed=len(failed_jobs),
            total_endpoints=len(all_endpoints)
        )
        
        return {
            "success": len(successful_jobs) > 0,
            "endpoints": all_endpoints,
            "summary": {
                "total_configs": len(configs),
                "successful": len(successful_jobs),
                "failed": len(failed_jobs),
                "total_endpoints": len(all_endpoints)
            },
            "successful_jobs": successful_jobs,
            "failed_jobs": failed_jobs
        }
    
    async def run_analysis_trajectories(
        self,
        lat: float,
        lon: float,
        mode: str = "backward",
        days: int = 2,
        heights: List[int] = None,
        time_interval_hours: int = 6
    ) -> Dict[str, Any]:
        """
        运行分析所需的全部轨迹
        
        这是主要的调用入口，自动生成配置并批量运行。
        
        Args:
            lat: 分析点纬度
            lon: 分析点经度
            mode: 分析模式 (backward/forward)
            days: 分析天数 (1-3)
            heights: 高度层列表
            time_interval_hours: 时间间隔
        
        Returns:
            包含所有轨迹端点的结果
        """
        # 生成配置
        configs = self.generate_trajectory_configs(
            lat=lat,
            lon=lon,
            mode=mode,
            days=days,
            heights=heights,
            time_interval_hours=time_interval_hours
        )
        
        # 批量运行
        result = await self.run_batch_trajectories(configs)
        
        # 添加元数据
        result["metadata"] = {
            "lat": lat,
            "lon": lon,
            "mode": mode,
            "days": days,
            "heights": heights or [100, 500, 1000],
            "time_interval_hours": time_interval_hours
        }
        
        return result
