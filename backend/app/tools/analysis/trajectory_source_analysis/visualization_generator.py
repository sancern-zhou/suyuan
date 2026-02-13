"""
轨迹源清单分析可视化生成器

生成Chart v3.1格式的可视化配置，包括：
- 轨迹地图（高德地图）
- 企业贡献柱状图
- 轨迹密度热力图
"""

from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


def _save_image_to_cache(base64_data: str, chart_id: Optional[str] = None) -> str:
    """将base64图片保存到缓存，返回image_id"""
    from app.services.image_cache import get_image_cache
    cache = get_image_cache()
    return cache.save(base64_data, chart_id)


def _get_full_image_url(image_id: str) -> str:
    """获取完整的图片访问URL（供LLM生成Markdown链接使用）"""
    from app.services.image_cache import get_image_cache
    cache = get_image_cache()
    # 返回完整URL路径，前端可渲染
    return f"/api/image/{image_id}"


def _create_image_visual(
    image_base64: str,
    chart_id: str,
    title: str,
    image_type: str,
    scenario: str,
    extra_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """将base64图片保存并创建VisualBlock格式输出"""
    saved_image_id = _save_image_to_cache(image_base64, chart_id)
    full_url = _get_full_image_url(saved_image_id)

    meta = {
        "schema_version": "3.1",
        "generator": "VisualizationGenerator",
        "scenario": scenario,
        "layout_hint": "wide",
        "image_type": image_type
    }
    if extra_meta:
        meta.update(extra_meta)

    return {
        "id": saved_image_id,
        "type": "image",
        "schema": "chart_config",
        "payload": {
            "id": saved_image_id,
            "type": "image",
            "title": title,
            "data": f"[IMAGE:{saved_image_id}]",  # Placeholder for LLM
            "image_id": saved_image_id,
            "image_url": full_url,  # 完整URL，供LLM生成Markdown链接
            "markdown_image": f"![{title}]({full_url})",  # 预生成的Markdown格式
            "meta": meta
        },
        "meta": {
            "schema_version": "v2.0",
            "generator": "VisualizationGenerator",
            "scenario": scenario,
            "image_id": saved_image_id,
            "image_url": full_url,
            ** (extra_meta or {})
        }
    }


class VisualizationGenerator:
    """
    可视化配置生成器
    
    生成UDF v2.0 + Chart v3.1格式的可视化配置。
    """
    
    def __init__(self):
        self.schema_version = "3.1"
        self.generator = "trajectory_source_analysis"
    
    def generate_trajectory_map(
        self,
        endpoints: List[Dict[str, Any]],
        top_contributors: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str
    ) -> Dict[str, Any]:
        """
        生成轨迹分析图片（替代交互式地图）

        使用matplotlib生成包含轨迹线、企业标记点和分析点的静态图片，
        避免交互式地图的性能问题。

        Args:
            endpoints: 轨迹端点数据
            top_contributors: 贡献排名企业
            target_location: 目标位置 {lat, lon}
            mode: 分析模式

        Returns:
            Chart v3.1图片配置（type="image"）
        """
        # 生成轨迹图片
        image_base64 = self._generate_trajectory_image(
            endpoints=endpoints,
            top_contributors=top_contributors,
            target_location=target_location,
            mode=mode
        )

        if not image_base64:
            logger.warning("trajectory_image_generation_failed")
            # 返回空配置作为fallback
            return {
                "id": "trajectory_map",
                "type": "image",
                "schema": "chart_config",
                "payload": {
                    "id": "trajectory_map",
                    "type": "image",
                    "title": f"{'后向轨迹溯源' if mode == 'backward' else '前向轨迹预测'}分析图",
                    "data": "",
                    "meta": {
                        "schema_version": self.schema_version,
                        "generator": self.generator,
                        "scenario": f"trajectory_{mode}",
                        "layout_hint": "wide",
                        "error": "图片生成失败"
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": self.generator,
                    "scenario": f"trajectory_{mode}"
                }
            }

        # 使用新方法创建VisualBlock
        chart_id = f"trajectory_map_{mode}_{self.schema_version}"
        return _create_image_visual(
            image_base64=image_base64,
            chart_id=chart_id,
            title=f"{'后向轨迹溯源' if mode == 'backward' else '前向轨迹预测'}分析图",
            image_type="trajectory_analysis",
            scenario=f"trajectory_{mode}",
            extra_meta={
                "components": ["heatmap", "trajectory_lines", "target_location"]
            }
        )
    
    def generate_contribution_bar_chart(
        self,
        top_contributors: List[Dict[str, Any]],
        pollutant: str
    ) -> Dict[str, Any]:
        """
        生成企业贡献柱状图
        
        Args:
            top_contributors: 贡献排名企业
            pollutant: 污染物类型
        
        Returns:
            Chart v3.1柱状图配置
        """
        # 准备数据
        names = []
        scores = []
        
        for ent in top_contributors[:10]:  # 只显示前10
            # 截断过长的企业名称
            name = ent["enterprise_name"]
            if len(name) > 15:
                name = name[:12] + "..."
            names.append(name)
            scores.append(float(ent["contribution_percent"].rstrip("%")))
        
        return {
            "id": "contribution_bar",
            "type": "bar",
            "schema": "chart_config",
            "payload": {
                "id": "contribution_bar",
                "type": "bar",
                "title": f"企业{pollutant}贡献排名",
                "data": {
                    "x": names,
                    "y": scores
                },
                "options": {
                    "xAxis": {
                        "name": "企业",
                        "axisLabel": {
                            "rotate": 45,
                            "interval": 0
                        }
                    },
                    "yAxis": {
                        "name": "贡献率 (%)",
                        "max": 100
                    },
                    "series": [{
                        "name": "贡献率",
                        "type": "bar",
                        "itemStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0, "y": 0, "x2": 0, "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": "#ff6b6b"},
                                    {"offset": 1, "color": "#feca57"}
                                ]
                            }
                        }
                    }]
                },
                "meta": {
                    "schema_version": self.schema_version,
                    "generator": self.generator,
                    "scenario": "contribution_ranking",
                    "layout_hint": "wide"
                }
            },
            "meta": {
                "schema_version": "v2.0",
                "generator": self.generator,
                "scenario": "contribution_ranking"
            }
        }
    
    def generate_industry_pie_chart(
        self,
        top_contributors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成行业分布饼图
        
        Args:
            top_contributors: 贡献排名企业
        
        Returns:
            Chart v3.1饼图配置
        """
        # 按行业汇总
        industry_scores = {}
        for ent in top_contributors:
            industry = ent.get("industry", "其他")
            score = float(ent["contribution_percent"].rstrip("%"))
            industry_scores[industry] = industry_scores.get(industry, 0) + score
        
        # 准备饼图数据
        pie_data = [
            {"name": industry, "value": round(score, 1)}
            for industry, score in sorted(industry_scores.items(), key=lambda x: -x[1])
        ]
        
        return {
            "id": "industry_pie",
            "type": "pie",
            "schema": "chart_config",
            "payload": {
                "id": "industry_pie",
                "type": "pie",
                "title": "行业贡献分布",
                "data": pie_data,
                "options": {
                    "radius": ["40%", "70%"],
                    "label": {
                        "show": True,
                        "formatter": "{b}: {d}%"
                    }
                },
                "meta": {
                    "schema_version": self.schema_version,
                    "generator": self.generator,
                    "scenario": "industry_distribution",
                    "layout_hint": "side"
                }
            },
            "meta": {
                "schema_version": "v2.0",
                "generator": self.generator,
                "scenario": "industry_distribution"
            }
        }
    
    def generate_all_visuals(
        self,
        endpoints: List[Dict[str, Any]],
        top_contributors: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str,
        pollutant: str
    ) -> List[Dict[str, Any]]:
        """
        生成所有可视化配置（分离显示方案）

        输出4个独立图表：
        1. 重点潜在源区分布图（主图，局部轨迹）
        2. 轨迹概览图（辅助，全范围轨迹）
        3. 企业贡献排名柱状图
        4. 行业分布饼图

        Args:
            endpoints: 轨迹端点
            top_contributors: 贡献排名
            target_location: 目标位置
            mode: 分析模式
            pollutant: 污染物

        Returns:
            可视化配置列表（4个图表）
        """
        visuals = []

        # 1. 重点潜在源区分布图（主图）
        if endpoints and top_contributors:
            visuals.append(self.generate_local_source_map(
                endpoints, top_contributors, target_location, mode
            ))

        # 2. 轨迹概览图（辅助）
        if endpoints:
            visuals.append(self.generate_trajectory_overview(
                endpoints, target_location, mode
            ))

        # 3. 企业贡献柱状图
        if top_contributors:
            visuals.append(self.generate_contribution_bar_chart(
                top_contributors, pollutant
            ))

        # 4. 行业饼图
        if top_contributors:
            visuals.append(self.generate_industry_pie_chart(top_contributors))

        logger.info(
            "visuals_generated",
            count=len(visuals),
            types=[v["type"] for v in visuals],
            note="分离显示方案：局部重点源区图 + 全范围轨迹概览"
        )

        return visuals
    
    def generate_local_source_map(
        self,
        endpoints: List[Dict[str, Any]],
        top_contributors: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str
    ) -> Dict[str, Any]:
        """
        生成重点潜在源区分布图（局部轨迹）

        显示目标位置周边区域（约50km范围），包含：
        - 局部轨迹线（浅色）
        - 企业热力图（贡献度聚合）
        - 企业标记点（Top 15）
        - 分析目标点

        Args:
            endpoints: 轨迹端点数据
            top_contributors: 贡献排名企业
            target_location: 目标位置
            mode: 分析模式

        Returns:
            Chart v3.1图片配置
        """
        image_base64 = self._generate_local_source_image(
            endpoints=endpoints,
            top_contributors=top_contributors,
            target_location=target_location,
            mode=mode
        )

        if not image_base64:
            return {
                "id": "local_source_map",
                "type": "image",
                "schema": "chart_config",
                "payload": {
                    "id": "local_source_map",
                    "type": "image",
                    "title": "重点潜在源区分布图",
                    "data": "",
                    "meta": {
                        "schema_version": self.schema_version,
                        "generator": self.generator,
                        "scenario": f"local_source_{mode}",
                        "layout_hint": "wide",
                        "error": "Local source map generation failed"
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": self.generator,
                    "scenario": f"local_source_{mode}"
                }
            }

        # 使用新方法创建VisualBlock
        chart_id = f"local_source_map_{mode}_{self.schema_version}"
        return _create_image_visual(
            image_base64=image_base64,
            chart_id=chart_id,
            title="重点潜在源区分布图",
            image_type="local_source_distribution",
            scenario=f"local_source_{mode}",
            extra_meta={
                "components": ["local_trajectories", "heatmap", "target_location"]
            }
        )

    def generate_trajectory_overview(
        self,
        endpoints: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str
    ) -> Dict[str, Any]:
        """
        生成轨迹概览图（全范围轨迹）

        显示完整轨迹路径，包含：
        - 全范围轨迹线（跨省/跨国）
        - 轨迹起点/终点标记
        - 分析目标点

        Args:
            endpoints: 轨迹端点数据
            target_location: 目标位置
            mode: 分析模式

        Returns:
            Chart v3.1图片配置
        """
        image_base64 = self._generate_trajectory_overview_image(
            endpoints=endpoints,
            target_location=target_location,
            mode=mode
        )

        if not image_base64:
            return {
                "id": "trajectory_overview",
                "type": "image",
                "schema": "chart_config",
                "payload": {
                    "id": "trajectory_overview",
                    "type": "image",
                    "title": f"{'后向轨迹' if mode == 'backward' else '前向轨迹'}概览图",
                    "data": "",
                    "meta": {
                        "schema_version": self.schema_version,
                        "generator": self.generator,
                        "scenario": f"trajectory_overview_{mode}",
                        "layout_hint": "wide",
                        "error": "Trajectory overview generation failed"
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": self.generator,
                    "scenario": f"trajectory_overview_{mode}"
                }
            }

        # 使用新方法创建VisualBlock
        chart_id = f"trajectory_overview_{mode}_{self.schema_version}"
        return _create_image_visual(
            image_base64=image_base64,
            chart_id=chart_id,
            title=f"{'后向轨迹' if mode == 'backward' else '前向轨迹'}概览图",
            image_type="trajectory_overview",
            scenario=f"trajectory_overview_{mode}",
            extra_meta={
                "components": ["full_trajectories", "start_end_markers", "target_location"]
            }
        )

    def _prepare_trajectory_lines(
        self,
        endpoints: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """准备轨迹线数据"""
        # 按轨迹ID分组
        trajectories = {}
        for ep in endpoints:
            traj_id = ep.get("trajectory_id", 1)
            batch_idx = ep.get("batch_index", 0)
            key = (traj_id, batch_idx)
            if key not in trajectories:
                trajectories[key] = []
            trajectories[key].append(ep)
        
        lines = []
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7"]
        
        for i, (key, points) in enumerate(trajectories.items()):
            # 按age_hours排序
            points = sorted(points, key=lambda x: x.get("age_hours", 0))
            
            path = [[p.get("lon", 0), p.get("lat", 0)] for p in points]
            
            if len(path) >= 2:
                lines.append({
                    "path": path,
                    "strokeColor": colors[i % len(colors)],
                    "strokeWeight": 2,
                    "strokeOpacity": 0.7
                })
        
        return lines
    
    def _prepare_enterprise_markers(
        self,
        top_contributors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """准备企业标记点数据"""
        markers = []
        
        for ent in top_contributors[:15]:
            loc = ent.get("location", {})
            if loc.get("lat") and loc.get("lon"):
                markers.append({
                    "position": [loc["lon"], loc["lat"]],
                    "title": ent["enterprise_name"],
                    "label": {
                        "content": f"#{ent['rank']}",
                        "direction": "top"
                    },
                    "extData": {
                        "rank": ent["rank"],
                        "industry": ent["industry"],
                        "contribution": ent["contribution_percent"]
                    }
                })
        
        return markers
    
    def _prepare_heatmap_data(
        self,
        top_contributors: List[Dict[str, Any]],
        grid_resolution: float = 0.05
    ) -> List[Dict[str, Any]]:
        """
        准备热力图数据（基于企业贡献度区域聚合）

        Args:
            top_contributors: 企业贡献排名列表
            grid_resolution: 网格分辨率（度），约5km

        Returns:
            热力图数据列表
        """
        if not top_contributors:
            return []

        # 按网格聚合企业贡献度
        grid_scores = {}

        for ent in top_contributors:
            loc = ent.get("location", {})
            lat = loc.get("lat")
            lon = loc.get("lon")

            if not lat or not lon:
                continue

            # 获取贡献分数
            score = ent.get("contribution_score", 0)
            if not score:
                # 从百分比解析
                percent_str = ent.get("contribution_percent", "0%")
                score = float(percent_str.rstrip("%"))

            # 网格化
            grid_key = (
                round(lat / grid_resolution) * grid_resolution,
                round(lon / grid_resolution) * grid_resolution
            )

            if grid_key not in grid_scores:
                grid_scores[grid_key] = 0
            grid_scores[grid_key] += score

        if not grid_scores:
            return []

        # 归一化
        max_score = max(grid_scores.values())

        heatmap_data = []
        for (lat, lon), score in grid_scores.items():
            heatmap_data.append({
                "lat": lat,
                "lng": lon,
                "score": score,
                "weight": score / max_score if max_score > 0 else 0
            })

        return heatmap_data
    
    def generate_recommendations(
        self,
        top_contributors: List[Dict[str, Any]],
        trajectory_summary: Dict[str, Any],
        mode: str,
        pollutant: str
    ) -> List[str]:
        """
        生成管控建议
        
        Args:
            top_contributors: 贡献排名
            trajectory_summary: 轨迹汇总
            mode: 分析模式
            pollutant: 污染物
        
        Returns:
            建议列表
        """
        recommendations = []
        
        if not top_contributors:
            recommendations.append("未识别到显著贡献源企业")
            return recommendations
        
        # 重点企业建议
        top1 = top_contributors[0]
        if mode == "backward":
            recommendations.append(
                f"【重点关注】{top1['enterprise_name']}，"
                f"{pollutant}贡献率{top1['contribution_percent']}，"
                f"建议优先核查其排放情况"
            )
        else:
            recommendations.append(
                f"【管控重点】{top1['enterprise_name']}，"
                f"预计{pollutant}影响贡献{top1['contribution_percent']}，"
                f"建议实施临时减排措施"
            )
        
        # 区域特征
        districts = {}
        for ent in top_contributors[:10]:
            district = ent.get("district", "未知")
            districts[district] = districts.get(district, 0) + 1
        
        if districts:
            top_district = max(districts, key=districts.get)
            recommendations.append(
                f"【区域特征】{top_district}企业群对当前污染贡献显著，"
                f"共{districts[top_district]}家企业进入贡献排名"
            )
        
        # 行业分布
        industries = {}
        for ent in top_contributors[:10]:
            industry = ent.get("industry", "未知")
            industries[industry] = industries.get(industry, 0) + 1
        
        if industries:
            top_industries = sorted(industries.items(), key=lambda x: -x[1])[:2]
            industry_str = "、".join([f"{ind}({cnt}家)" for ind, cnt in top_industries])
            recommendations.append(
                f"【行业分布】主要贡献行业：{industry_str}"
            )
        
        # 管控建议
        if mode == "backward":
            recommendations.append(
                f"【溯源建议】建议对排名前5企业开展现场核查，"
                f"重点检查{pollutant}排放设施运行情况"
            )
        else:
            recommendations.append(
                f"【管控建议】建议对排名前5企业实施临时减排措施，"
                f"预计可有效降低下游{pollutant}污染影响"
            )

        return recommendations

    def _generate_trajectory_image(
        self,
        endpoints: List[Dict[str, Any]],
        top_contributors: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str
    ) -> Optional[str]:
        """
        生成重点潜在源区分布图（base64编码）

        图层顺序（从底到顶）：
        1. 地图背景
        2. 轨迹线（浅色，显示气流路径）
        3. 热力图（企业贡献度区域聚合，显示重点源区）
        4. 企业标记点（Top 15）
        5. 分析点（目标位置）

        Args:
            endpoints: 轨迹端点数据
            top_contributors: 贡献排名企业
            target_location: 目标位置
            mode: 分析模式

        Returns:
            base64编码的PNG图片字符串，或None
        """
        if not endpoints:
            return None

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.colors import LinearSegmentedColormap
            from io import BytesIO
            import base64

            # 尝试导入cartopy用于地图背景
            use_cartopy = False
            try:
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                use_cartopy = True
                logger.info("using_cartopy_for_trajectory_background")
            except ImportError:
                logger.warning("cartopy_not_available", note="Using simple plot without map background")

            # 按轨迹ID分组
            trajectories = {}
            for ep in endpoints:
                traj_id = ep.get("trajectory_id", 1)
                batch_idx = ep.get("batch_index", 0)
                key = (traj_id, batch_idx)
                if key not in trajectories:
                    trajectories[key] = []
                trajectories[key].append(ep)

            # 计算地图范围
            all_lats = [ep["lat"] for ep in endpoints]
            all_lons = [ep["lon"] for ep in endpoints]
            # 包含企业标记点
            for ent in top_contributors[:15]:
                loc = ent.get("location", {})
                if loc.get("lat") and loc.get("lon"):
                    all_lats.append(loc["lat"])
                    all_lons.append(loc["lon"])

            lat_min, lat_max = min(all_lats), max(all_lats)
            lon_min, lon_max = min(all_lons), max(all_lons)

            lat_margin = (lat_max - lat_min) * 0.15 + 0.5
            lon_margin = (lon_max - lon_min) * 0.15 + 0.5

            extent = [lon_min - lon_margin, lon_max + lon_margin,
                     lat_min - lat_margin, lat_max + lat_margin]

            # 创建图形（单图，无高度剖面）
            if use_cartopy:
                fig = plt.figure(figsize=(12, 10))
                ax_map = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                ax_map.set_extent(extent, crs=ccrs.PlateCarree())

                # 添加地图要素
                ax_map.add_feature(cfeature.LAND, facecolor='#f5f5f5', edgecolor='none')
                ax_map.add_feature(cfeature.OCEAN, facecolor='#e6f3ff')
                ax_map.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='#333333')
                ax_map.add_feature(cfeature.BORDERS, linewidth=0.6, linestyle='--', edgecolor='#666666')
                ax_map.add_feature(cfeature.LAKES, facecolor='#e6f3ff', edgecolor='#333333', linewidth=0.3)

                try:
                    ax_map.add_feature(cfeature.STATES, linewidth=0.3, linestyle=':', edgecolor='#999999')
                except:
                    pass

                # 网格线
                gl = ax_map.gridlines(draw_labels=True, linewidth=0.4, color='gray', alpha=0.6, linestyle='--')
                gl.top_labels = False
                gl.right_labels = False
            else:
                fig, ax_map = plt.subplots(1, 1, figsize=(12, 10))
                ax_map.set_xlim(extent[0], extent[1])
                ax_map.set_ylim(extent[2], extent[3])
                ax_map.grid(True, linestyle='--', alpha=0.5)
                ax_map.set_xlabel('Longitude')
                ax_map.set_ylabel('Latitude')

            # ===== 图层1: 轨迹线（浅色，底层）=====
            light_colors = ['#b0b0b0', '#a0a0a0', '#909090', '#808080', '#707070']  # 浅灰色系
            for i, (key, points) in enumerate(sorted(trajectories.items())):
                points = sorted(points, key=lambda x: x.get("age_hours", 0))
                lats = [p["lat"] for p in points]
                lons = [p["lon"] for p in points]

                color = light_colors[i % len(light_colors)]

                if use_cartopy:
                    ax_map.plot(lons, lats, '-', color=color, linewidth=1.5,
                               alpha=0.6, transform=ccrs.PlateCarree(), zorder=2)
                else:
                    ax_map.plot(lons, lats, '-', color=color, linewidth=1.5,
                               alpha=0.6, zorder=2)

            # ===== 图层2: 热力图（企业贡献度区域聚合）=====
            heatmap_data = self._prepare_heatmap_data(top_contributors)
            if heatmap_data and len(heatmap_data) >= 1:
                heat_lons = [d['lng'] for d in heatmap_data]
                heat_lats = [d['lat'] for d in heatmap_data]
                heat_weights = [d['weight'] for d in heatmap_data]
                heat_scores = [d['score'] for d in heatmap_data]

                # 点大小随贡献度变化（最小100，最大800）
                sizes = [max(100, min(800, w * 700 + 100)) for w in heat_weights]

                if use_cartopy:
                    scatter = ax_map.scatter(
                        heat_lons, heat_lats,
                        c=heat_weights,
                        cmap='YlOrRd',
                        s=sizes,
                        alpha=0.7,
                        edgecolors='white',
                        linewidths=0.5,
                        transform=ccrs.PlateCarree(),
                        zorder=3
                    )
                else:
                    scatter = ax_map.scatter(
                        heat_lons, heat_lats,
                        c=heat_weights,
                        cmap='YlOrRd',
                        s=sizes,
                        alpha=0.7,
                        edgecolors='white',
                        linewidths=0.5,
                        zorder=3
                    )

                # 颜色条
                cbar = plt.colorbar(scatter, ax=ax_map, shrink=0.6, pad=0.02)
                cbar.set_label('Contribution', fontsize=10)

            # ===== 图层3: 分析点（目标位置）=====
            target_lon = target_location.get("lon", 113.26)
            target_lat = target_location.get("lat", 23.13)

            if use_cartopy:
                ax_map.plot(target_lon, target_lat, '*', color='#3498db', markersize=25,
                           markeredgecolor='white', markeredgewidth=2,
                           transform=ccrs.PlateCarree(), zorder=7, label='Analysis Point')
            else:
                ax_map.plot(target_lon, target_lat, '*', color='#3498db', markersize=25,
                           markeredgecolor='white', markeredgewidth=2, zorder=7, label='Analysis Point')

            # 图例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], color='#a0a0a0', linewidth=2, label='Trajectory'),
                Line2D([0], [0], marker='*', color='w', markerfacecolor='#3498db',
                       markersize=15, label='Analysis Point')
            ]
            ax_map.legend(handles=legend_elements, loc='upper right', fontsize=10)

            # 标题
            mode_text = '后向轨迹溯源' if mode == 'backward' else '前向轨迹预测'
            fig.suptitle(
                f'重点潜在源区分布图 - {mode_text} | ({target_lat:.2f}, {target_lon:.2f})',
                fontsize=14, fontweight='bold', y=0.95
            )

            # 底部信息
            fig.text(0.5, 0.02,
                    f'{len(trajectories)} trajectories | {len(top_contributors)} enterprises',
                    ha='center', fontsize=9, style='italic', color='gray')

            # 保存到内存
            plt.tight_layout()
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            logger.info("trajectory_image_generated",
                       size_kb=len(image_base64) / 1024,
                       trajectories=len(trajectories),
                       enterprises=len(top_contributors),
                       heatmap_grids=len(heatmap_data) if heatmap_data else 0)

            return image_base64

        except Exception as e:
            logger.error("trajectory_image_generation_failed", error=str(e))
            import traceback
            logger.error("trajectory_image_traceback", traceback=traceback.format_exc())
            return None

    def _generate_local_source_image(
        self,
        endpoints: List[Dict[str, Any]],
        top_contributors: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str,
        radius_km: float = 25.0
    ) -> Optional[str]:
        """
        生成重点潜在源区分布图（局部范围）

        仅显示目标位置周边radius_km范围内的轨迹和企业，
        提供更清晰的重点源区分布视图。

        Args:
            endpoints: 轨迹端点数据
            top_contributors: 贡献排名企业
            target_location: 目标位置
            mode: 分析模式
            radius_km: 显示半径（km），默认25km（约0.25度）

        Returns:
            base64编码的PNG图片字符串，或None
        """
        if not endpoints or not top_contributors:
            return None

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from io import BytesIO
            import base64
            import math

            # 计算距离函数（简化版）
            def haversine_km(lat1, lon1, lat2, lon2):
                R = 6371  # 地球半径km
                dlat = math.radians(lat2 - lat1)
                dlon = math.radians(lon2 - lon1)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
                return R * 2 * math.asin(math.sqrt(a))

            target_lat = target_location.get("lat", 23.13)
            target_lon = target_location.get("lon", 113.26)

            # 过滤轨迹点：只保留radius_km范围内的
            local_endpoints = []
            for ep in endpoints:
                dist = haversine_km(target_lat, target_lon, ep["lat"], ep["lon"])
                if dist <= radius_km:
                    local_endpoints.append(ep)

            # 尝试导入cartopy
            use_cartopy = False
            try:
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                use_cartopy = True
            except ImportError:
                pass

            # 按轨迹ID分组
            trajectories = {}
            for ep in local_endpoints:
                traj_id = ep.get("trajectory_id", 1)
                batch_idx = ep.get("batch_index", 0)
                key = (traj_id, batch_idx)
                if key not in trajectories:
                    trajectories[key] = []
                trajectories[key].append(ep)

            # 计算局部范围：以目标点为中心，固定半径
            # 1度约111km，所以radius_km对应约 radius_km/111 度
            degree_radius = radius_km / 111.0 * 1.2  # 增加20%边距

            lat_min = target_lat - degree_radius
            lat_max = target_lat + degree_radius
            lon_min = target_lon - degree_radius
            lon_max = target_lon + degree_radius

            # 添加少量边距
            lat_margin = 0.02
            lon_margin = 0.02

            extent = [lon_min - lon_margin, lon_max + lon_margin,
                     lat_min - lat_margin, lat_max + lat_margin]

            # 创建图形
            if use_cartopy:
                fig = plt.figure(figsize=(12, 10))
                ax_map = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                ax_map.set_extent(extent, crs=ccrs.PlateCarree())

                ax_map.add_feature(cfeature.LAND, facecolor='#f5f5f5', edgecolor='none')
                ax_map.add_feature(cfeature.OCEAN, facecolor='#e6f3ff')
                ax_map.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='#333333')
                ax_map.add_feature(cfeature.BORDERS, linewidth=0.6, linestyle='--', edgecolor='#666666')

                try:
                    ax_map.add_feature(cfeature.STATES, linewidth=0.3, linestyle=':', edgecolor='#999999')
                except:
                    pass

                gl = ax_map.gridlines(draw_labels=True, linewidth=0.4, color='gray', alpha=0.6, linestyle='--')
                gl.top_labels = False
                gl.right_labels = False
            else:
                fig, ax_map = plt.subplots(1, 1, figsize=(12, 10))
                ax_map.set_xlim(extent[0], extent[1])
                ax_map.set_ylim(extent[2], extent[3])
                ax_map.grid(True, linestyle='--', alpha=0.5)
                ax_map.set_xlabel('Longitude')
                ax_map.set_ylabel('Latitude')

            # 图层1: 局部轨迹线（浅色）
            light_colors = ['#b0b0b0', '#a0a0a0', '#909090', '#808080', '#707070']
            for i, (key, points) in enumerate(sorted(trajectories.items())):
                points = sorted(points, key=lambda x: x.get("age_hours", 0))
                lats = [p["lat"] for p in points]
                lons = [p["lon"] for p in points]

                if len(lats) >= 2:
                    color = light_colors[i % len(light_colors)]
                    if use_cartopy:
                        ax_map.plot(lons, lats, '-', color=color, linewidth=1.5,
                                   alpha=0.6, transform=ccrs.PlateCarree(), zorder=2)
                    else:
                        ax_map.plot(lons, lats, '-', color=color, linewidth=1.5,
                                   alpha=0.6, zorder=2)

            # 图层2: 热力图（企业贡献度区域聚合）
            heatmap_data = self._prepare_heatmap_data(top_contributors, grid_resolution=0.02)  # 更细的网格
            if heatmap_data and len(heatmap_data) >= 1:
                heat_lons = [d['lng'] for d in heatmap_data]
                heat_lats = [d['lat'] for d in heatmap_data]
                heat_weights = [d['weight'] for d in heatmap_data]

                # 局部图使用更大的点
                sizes = [max(200, min(1200, w * 1000 + 200)) for w in heat_weights]

                if use_cartopy:
                    scatter = ax_map.scatter(
                        heat_lons, heat_lats,
                        c=heat_weights, cmap='YlOrRd', s=sizes,
                        alpha=0.7, edgecolors='white', linewidths=0.5,
                        transform=ccrs.PlateCarree(), zorder=3
                    )
                else:
                    scatter = ax_map.scatter(
                        heat_lons, heat_lats,
                        c=heat_weights, cmap='YlOrRd', s=sizes,
                        alpha=0.7, edgecolors='white', linewidths=0.5, zorder=3
                    )

                cbar = plt.colorbar(scatter, ax=ax_map, shrink=0.6, pad=0.02)
                cbar.set_label('Contribution', fontsize=10)

            # 图层4: 分析点
            if use_cartopy:
                ax_map.plot(target_lon, target_lat, '*', color='#3498db', markersize=28,
                           markeredgecolor='white', markeredgewidth=2,
                           transform=ccrs.PlateCarree(), zorder=7)
            else:
                ax_map.plot(target_lon, target_lat, '*', color='#3498db', markersize=28,
                           markeredgecolor='white', markeredgewidth=2, zorder=7)

            # 图例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], color='#a0a0a0', linewidth=2, label='Local Trajectory'),
                Line2D([0], [0], marker='*', color='w', markerfacecolor='#3498db',
                       markersize=15, label='Analysis Point')
            ]
            ax_map.legend(handles=legend_elements, loc='upper right', fontsize=10)

            # 标题
            mode_text = 'Backward' if mode == 'backward' else 'Forward'
            fig.suptitle(
                f'Key Source Distribution ({radius_km:.0f}km radius) | {mode_text}',
                fontsize=14, fontweight='bold', y=0.95
            )

            # 底部信息
            fig.text(0.5, 0.02,
                    f'{len(trajectories)} local trajectories | {len(top_contributors)} enterprises in {radius_km:.0f}km | Center: ({target_lat:.2f}, {target_lon:.2f})',
                    ha='center', fontsize=9, style='italic', color='gray')

            plt.tight_layout()
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            logger.info("local_source_image_generated",
                       size_kb=len(image_base64) / 1024,
                       local_trajectories=len(trajectories),
                       enterprises=len(top_contributors),
                       radius_km=radius_km)

            return image_base64

        except Exception as e:
            logger.error("local_source_image_generation_failed", error=str(e))
            import traceback
            logger.error("local_source_image_traceback", traceback=traceback.format_exc())
            return None

    def _generate_trajectory_overview_image(
        self,
        endpoints: List[Dict[str, Any]],
        target_location: Dict[str, float],
        mode: str
    ) -> Optional[str]:
        """
        生成轨迹概览图（全范围）

        显示完整轨迹路径，适合查看跨省/跨国传输路径。

        Args:
            endpoints: 轨迹端点数据
            target_location: 目标位置
            mode: 分析模式

        Returns:
            base64编码的PNG图片字符串，或None
        """
        if not endpoints:
            return None

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from io import BytesIO
            import base64

            # 尝试导入cartopy
            use_cartopy = False
            try:
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                use_cartopy = True
            except ImportError:
                pass

            # 按轨迹ID分组
            trajectories = {}
            for ep in endpoints:
                traj_id = ep.get("trajectory_id", 1)
                batch_idx = ep.get("batch_index", 0)
                key = (traj_id, batch_idx)
                if key not in trajectories:
                    trajectories[key] = []
                trajectories[key].append(ep)

            # 计算全范围
            all_lats = [ep["lat"] for ep in endpoints]
            all_lons = [ep["lon"] for ep in endpoints]

            target_lat = target_location.get("lat", 23.13)
            target_lon = target_location.get("lon", 113.26)
            all_lats.append(target_lat)
            all_lons.append(target_lon)

            lat_min, lat_max = min(all_lats), max(all_lats)
            lon_min, lon_max = min(all_lons), max(all_lons)

            lat_margin = (lat_max - lat_min) * 0.1 + 1.0
            lon_margin = (lon_max - lon_min) * 0.1 + 1.0

            extent = [lon_min - lon_margin, lon_max + lon_margin,
                     lat_min - lat_margin, lat_max + lat_margin]

            # 创建图形
            if use_cartopy:
                fig = plt.figure(figsize=(14, 10))
                ax_map = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                ax_map.set_extent(extent, crs=ccrs.PlateCarree())

                ax_map.add_feature(cfeature.LAND, facecolor='#f0f0f0', edgecolor='none')
                ax_map.add_feature(cfeature.OCEAN, facecolor='#d4e6f1')
                ax_map.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='#333333')
                ax_map.add_feature(cfeature.BORDERS, linewidth=0.6, linestyle='--', edgecolor='#666666')
                ax_map.add_feature(cfeature.LAKES, facecolor='#d4e6f1', edgecolor='#333333', linewidth=0.3)

                try:
                    ax_map.add_feature(cfeature.STATES, linewidth=0.3, linestyle=':', edgecolor='#999999')
                except:
                    pass

                gl = ax_map.gridlines(draw_labels=True, linewidth=0.4, color='gray', alpha=0.6, linestyle='--')
                gl.top_labels = False
                gl.right_labels = False
            else:
                fig, ax_map = plt.subplots(1, 1, figsize=(14, 10))
                ax_map.set_xlim(extent[0], extent[1])
                ax_map.set_ylim(extent[2], extent[3])
                ax_map.grid(True, linestyle='--', alpha=0.5)
                ax_map.set_xlabel('Longitude')
                ax_map.set_ylabel('Latitude')

            # 轨迹线（彩色，区分不同轨迹）
            traj_colors = ['#3498db', '#2ecc71', '#e74c3c', '#9b59b6', '#f39c12',
                          '#1abc9c', '#e67e22', '#34495e', '#27ae60', '#c0392b']

            for i, (key, points) in enumerate(sorted(trajectories.items())):
                points = sorted(points, key=lambda x: x.get("age_hours", 0))
                lats = [p["lat"] for p in points]
                lons = [p["lon"] for p in points]

                if len(lats) >= 2:
                    color = traj_colors[i % len(traj_colors)]
                    if use_cartopy:
                        ax_map.plot(lons, lats, '-', color=color, linewidth=2.0,
                                   alpha=0.8, transform=ccrs.PlateCarree(), zorder=2)
                        # 起点标记（小圆点）
                        ax_map.plot(lons[0], lats[0], 'o', color=color, markersize=6,
                                   markeredgecolor='white', markeredgewidth=1,
                                   transform=ccrs.PlateCarree(), zorder=3)
                    else:
                        ax_map.plot(lons, lats, '-', color=color, linewidth=2.0,
                                   alpha=0.8, zorder=2)
                        ax_map.plot(lons[0], lats[0], 'o', color=color, markersize=6,
                                   markeredgecolor='white', markeredgewidth=1, zorder=3)

            # 分析点（目标位置）
            if use_cartopy:
                ax_map.plot(target_lon, target_lat, '*', color='#e74c3c', markersize=30,
                           markeredgecolor='white', markeredgewidth=2,
                           transform=ccrs.PlateCarree(), zorder=5)
            else:
                ax_map.plot(target_lon, target_lat, '*', color='#e74c3c', markersize=30,
                           markeredgecolor='white', markeredgewidth=2, zorder=5)

            # 图例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], color='#3498db', linewidth=2, label='Trajectory'),
                Line2D([0], [0], marker='o', color='w', markerfacecolor='#3498db',
                       markersize=8, label='Start Point'),
                Line2D([0], [0], marker='*', color='w', markerfacecolor='#e74c3c',
                       markersize=15, label='Analysis Point')
            ]
            ax_map.legend(handles=legend_elements, loc='upper right', fontsize=10)

            # 标题
            mode_text = 'Backward Trajectory' if mode == 'backward' else 'Forward Trajectory'
            fig.suptitle(
                f'{mode_text} Overview | {len(trajectories)} trajectories',
                fontsize=14, fontweight='bold', y=0.95
            )

            # 底部信息
            lat_range = lat_max - lat_min
            lon_range = lon_max - lon_min
            fig.text(0.5, 0.02,
                    f'Coverage: {lat_range:.1f} deg lat x {lon_range:.1f} deg lon | Target: ({target_lat:.2f}, {target_lon:.2f})',
                    ha='center', fontsize=9, style='italic', color='gray')

            plt.tight_layout()
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='white')
            plt.close(fig)

            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            logger.info("trajectory_overview_image_generated",
                       size_kb=len(image_base64) / 1024,
                       trajectories=len(trajectories),
                       lat_range=lat_range,
                       lon_range=lon_range)

            return image_base64

        except Exception as e:
            logger.error("trajectory_overview_image_generation_failed", error=str(e))
            import traceback
            logger.error("trajectory_overview_traceback", traceback=traceback.format_exc())
            return None
