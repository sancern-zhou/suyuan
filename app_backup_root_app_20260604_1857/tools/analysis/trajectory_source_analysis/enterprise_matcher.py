"""
轨迹-企业匹配器

负责将轨迹点与企业源清单进行空间匹配，计算贡献权重。

特性：
- 轨迹点插值（解决盲区问题）
- 网格化批量查询（优化API调用）
- 多因子加权打分
"""

from typing import Dict, Any, List, Tuple
from math import radians, sin, cos, sqrt, atan2, exp, log
import asyncio
import structlog

from app.utils.http_client import http_client
from config.settings import settings

logger = structlog.get_logger()


class EnterpriseMatcher:
    """
    企业匹配器
    
    将轨迹端点与企业源清单进行空间匹配，
    计算每个企业对污染的贡献权重。
    """
    
    def __init__(
        self,
        enterprise_api_base: str = None,
        search_radius_km: float = 5.0,
        interpolation_interval_km: float = 10.0,  # 从5km增加到10km，减少插值点
        grid_resolution: float = 0.2,  # 从0.1度增加到0.2度（约20km），减少网格数
        max_height_m: float = 1500.0
    ):
        """
        初始化匹配器

        Args:
            enterprise_api_base: 企业API地址
            search_radius_km: 搜索半径（公里）
            interpolation_interval_km: 插值间隔（公里）- 增加以减少点数量
            grid_resolution: 网格分辨率（度）- 增加以减少查询次数
            max_height_m: 最大有效高度（米）
        """
        self.enterprise_api_base = enterprise_api_base or "http://180.184.91.74:9095"
        self.search_radius_km = search_radius_km
        self.interpolation_interval_km = interpolation_interval_km
        self.grid_resolution = grid_resolution
        self.max_height_m = max_height_m
    
    @staticmethod
    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算两点间的球面距离（公里）
        
        使用Haversine公式。
        """
        R = 6371  # 地球半径（公里）
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1-a))
    
    def interpolate_trajectory_points(
        self,
        endpoints: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        在轨迹点之间插入中间点，确保无盲区
        
        问题：NOAA端点每小时1个，点间距可达30-40km
        解决：按固定间隔插值，确保完整覆盖
        
        Args:
            endpoints: 原始轨迹端点列表
        
        Returns:
            插值后的轨迹点列表
        """
        if not endpoints or len(endpoints) < 2:
            return endpoints
        
        # 按轨迹ID分组
        trajectories = {}
        for ep in endpoints:
            traj_id = ep.get("trajectory_id", 1)
            if traj_id not in trajectories:
                trajectories[traj_id] = []
            trajectories[traj_id].append(ep)
        
        # 对每条轨迹进行插值
        interpolated = []
        
        for traj_id, points in trajectories.items():
            # 按age_hours排序
            points = sorted(points, key=lambda x: x.get("age_hours", 0))
            
            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]

                # 计算两点间距离
                distance = self.haversine(
                    p1.get("lat", 0), p1.get("lon", 0),
                    p2.get("lat", 0), p2.get("lon", 0)
                )

                # 计算需要插入的点数 - 优化：最少插值1个，最多5个
                n_points = max(1, min(5, int(distance / self.interpolation_interval_km)))

                for j in range(n_points):
                    ratio = j / n_points
                    interpolated.append({
                        "lat": p1.get("lat", 0) + (p2.get("lat", 0) - p1.get("lat", 0)) * ratio,
                        "lon": p1.get("lon", 0) + (p2.get("lon", 0) - p1.get("lon", 0)) * ratio,
                        "height": p1.get("height", 0) + (p2.get("height", 0) - p1.get("height", 0)) * ratio,
                        "age_hours": p1.get("age_hours", 0) + (p2.get("age_hours", 0) - p1.get("age_hours", 0)) * ratio,
                        "trajectory_id": traj_id,
                        "batch_index": p1.get("batch_index", 0),
                        "is_interpolated": j > 0
                    })
            
            # 添加最后一个点
            if points:
                last_point = points[-1].copy()
                last_point["is_interpolated"] = False
                interpolated.append(last_point)
        
        logger.info(
            "trajectory_interpolation_complete",
            original_count=len(endpoints),
            interpolated_count=len(interpolated),
            interval_km=self.interpolation_interval_km
        )
        
        return interpolated
    
    def group_points_by_grid(
        self,
        points: List[Dict[str, Any]]
    ) -> Dict[Tuple[float, float], List[Dict[str, Any]]]:
        """
        将轨迹点按网格分组
        
        Args:
            points: 轨迹点列表
        
        Returns:
            网格分组字典 {(grid_lat, grid_lon): [points]}
        """
        grids = {}
        
        for point in points:
            # 高度过滤
            if point.get("height", 0) > self.max_height_m:
                continue
            
            # 计算网格键
            grid_key = (
                round(point["lat"] / self.grid_resolution) * self.grid_resolution,
                round(point["lon"] / self.grid_resolution) * self.grid_resolution
            )
            
            if grid_key not in grids:
                grids[grid_key] = []
            grids[grid_key].append(point)
        
        logger.info(
            "points_grouped_by_grid",
            total_points=len(points),
            grid_count=len(grids),
            resolution=self.grid_resolution
        )
        
        return grids
    
    async def query_enterprises_for_grid(
        self,
        grid_lat: float,
        grid_lon: float
    ) -> List[Dict[str, Any]]:
        """
        查询单个网格的企业
        
        Args:
            grid_lat: 网格中心纬度
            grid_lon: 网格中心经度
        
        Returns:
            企业列表
        """
        try:
            # 搜索半径 = 网格对角线一半 + 搜索半径
            grid_diagonal_km = self.grid_resolution * 111 * 1.414 / 2
            total_radius = grid_diagonal_km + self.search_radius_km
            
            response = await http_client.get(
                f"{self.enterprise_api_base}/api/enterprises/by-coordinates",
                params={
                    "lat": grid_lat,
                    "lon": grid_lon,
                    "max_distance": total_radius,
                    "max_results": 100  # 减少返回数量
                }
            )
            
            if isinstance(response, dict):
                return response.get("data", [])
            return []
            
        except Exception as e:
            logger.error(
                "enterprise_query_failed",
                grid_lat=grid_lat,
                grid_lon=grid_lon,
                error=str(e)
            )
            return []
    
    async def batch_query_enterprises(
        self,
        grids: Dict[Tuple[float, float], List[Dict[str, Any]]]
    ) -> Dict[Tuple[float, float], List[Dict[str, Any]]]:
        """
        批量查询所有网格的企业
        
        Args:
            grids: 网格分组
        
        Returns:
            网格企业字典 {(grid_lat, grid_lon): [enterprises]}
        """
        grid_enterprises = {}

        # 并发查询（限制并发数为3，减少API压力）
        semaphore = asyncio.Semaphore(3)
        
        async def query_with_limit(grid_key):
            async with semaphore:
                grid_lat, grid_lon = grid_key
                enterprises = await self.query_enterprises_for_grid(grid_lat, grid_lon)
                return grid_key, enterprises
        
        tasks = [query_with_limit(key) for key in grids.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                continue
            grid_key, enterprises = result
            grid_enterprises[grid_key] = enterprises
        
        total_enterprises = sum(len(e) for e in grid_enterprises.values())
        logger.info(
            "batch_enterprise_query_complete",
            grid_count=len(grids),
            total_enterprises=total_enterprises
        )
        
        return grid_enterprises
    
    def calculate_contribution_weight(
        self,
        distance_km: float,
        height_m: float,
        emission_rate: float,
        age_hours: float
    ) -> float:
        """
        计算单个轨迹点对企业的贡献权重
        
        权重 = 距离衰减 × 高度衰减 × 排放量 × 时间衰减
        
        Args:
            distance_km: 距离（公里）
            height_m: 高度（米）
            emission_rate: 排放速率（吨/年）
            age_hours: 轨迹年龄（小时）
        
        Returns:
            贡献权重
        """
        # 距离衰减：高斯衰减，5km为特征距离
        distance_weight = exp(-(distance_km ** 2) / (2 * 5 ** 2))
        
        # 高度衰减：指数衰减，500m为特征高度
        height_weight = exp(-height_m / 500)
        
        # 排放量权重：对数缩放避免极端值
        if emission_rate > 0:
            emission_weight = log(emission_rate + 1) + 1
        else:
            emission_weight = 0.1
        
        # 时间衰减：越近的轨迹点权重越大
        time_weight = exp(-abs(age_hours) / 24)
        
        return distance_weight * height_weight * emission_weight * time_weight
    
    async def match_trajectories_to_enterprises(
        self,
        endpoints: List[Dict[str, Any]],
        pollutant: str = "VOCs"
    ) -> Dict[str, Dict[str, Any]]:
        """
        将轨迹点与企业进行匹配
        
        完整流程：
        1. 轨迹点插值
        2. 网格化分组
        3. 批量查询企业
        4. 精确匹配+加权打分
        
        Args:
            endpoints: 原始轨迹端点
            pollutant: 关注的污染物类型
        
        Returns:
            企业贡献字典 {企业名称: {info, weight, passes}}
        """
        if not endpoints:
            return {}
        
        # Step 1: 轨迹点插值
        interpolated = self.interpolate_trajectory_points(endpoints)
        
        # Step 2: 网格化分组
        grids = self.group_points_by_grid(interpolated)
        
        if not grids:
            logger.warning("no_valid_points_after_filtering")
            return {}
        
        # Step 3: 批量查询企业
        grid_enterprises = await self.batch_query_enterprises(grids)
        
        # Step 4: 精确匹配 + 加权打分
        contributions = {}
        
        for grid_key, points in grids.items():
            enterprises = grid_enterprises.get(grid_key, [])
            
            for point in points:
                for ent in enterprises:
                    # 精确距离计算
                    distance = self.haversine(
                        point["lat"], point["lon"],
                        ent.get("纬度", 0), ent.get("经度", 0)
                    )
                    
                    # 距离过滤
                    if distance > self.search_radius_km:
                        continue
                    
                    ent_name = ent.get("企业名称", "未知企业")
                    emission_info = ent.get("排放信息", {})
                    emission = emission_info.get(pollutant, 0)
                    
                    # 权重计算
                    weight = self.calculate_contribution_weight(
                        distance_km=distance,
                        height_m=point.get("height", 0),
                        emission_rate=emission,
                        age_hours=abs(point.get("age_hours", 0))
                    )
                    
                    if ent_name not in contributions:
                        contributions[ent_name] = {
                            "enterprise_info": ent,
                            "total_weight": 0,
                            "trajectory_passes": 0,
                            "pass_details": []
                        }
                    
                    contributions[ent_name]["total_weight"] += weight
                    contributions[ent_name]["trajectory_passes"] += 1
                    contributions[ent_name]["pass_details"].append({
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "height": point.get("height", 0),
                        "age_hours": point.get("age_hours"),
                        "distance_km": round(distance, 2),
                        "weight": weight
                    })
        
        logger.info(
            "trajectory_enterprise_matching_complete",
            interpolated_points=len(interpolated),
            matched_enterprises=len(contributions),
            pollutant=pollutant
        )
        
        return contributions
    
    def rank_contributions(
        self,
        contributions: Dict[str, Dict[str, Any]],
        top_n: int = 15
    ) -> List[Dict[str, Any]]:
        """
        对企业贡献进行排序和归一化
        
        Args:
            contributions: 企业贡献字典
            top_n: 返回前N个企业
        
        Returns:
            排名后的企业列表
        """
        if not contributions:
            return []
        
        # 按总权重排序
        sorted_enterprises = sorted(
            contributions.items(),
            key=lambda x: x[1]["total_weight"],
            reverse=True
        )[:top_n]
        
        # 计算总权重用于归一化
        total_weight = sum(c[1]["total_weight"] for c in sorted_enterprises)
        
        result = []
        for rank, (name, data) in enumerate(sorted_enterprises, 1):
            contribution_percent = (data["total_weight"] / total_weight * 100) if total_weight > 0 else 0
            
            ent_info = data["enterprise_info"]
            pass_details = data["pass_details"]
            
            result.append({
                "rank": rank,
                "enterprise_name": name,
                "industry": ent_info.get("行业", "未知"),
                "location": {
                    "lat": ent_info.get("纬度"),
                    "lon": ent_info.get("经度")
                },
                "city": ent_info.get("城市", ""),
                "district": ent_info.get("区县", ""),
                "contribution_score": round(data["total_weight"], 4),
                "contribution_percent": f"{contribution_percent:.1f}%",
                "trajectory_passes": data["trajectory_passes"],
                "emission_info": ent_info.get("排放信息", {}),
                "avg_pass_height_m": round(
                    sum(p["height"] for p in pass_details) / len(pass_details), 1
                ) if pass_details else 0,
                "avg_pass_distance_km": round(
                    sum(p["distance_km"] for p in pass_details) / len(pass_details), 2
                ) if pass_details else 0
            })
        
        logger.info(
            "contribution_ranking_complete",
            total_matched=len(contributions),
            top_n=top_n,
            top1_percent=result[0]["contribution_percent"] if result else "N/A"
        )
        
        return result
