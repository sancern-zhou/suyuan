"""
轨迹+源清单分析工具

基于HYSPLIT后向/前向轨迹结合企业源清单，实现科学的污染溯源和管控预测。

功能：
1. backward模式：分析过去1-3天，识别潜在贡献源企业
2. forward模式：预测未来1-3天，给出管控建议

架构：Context-Aware V2 + UDF v2.0 + Chart v3.1
版本：1.0.0
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.analysis.trajectory_source_analysis.trajectory_runner import TrajectoryRunner
from app.tools.analysis.trajectory_source_analysis.enterprise_matcher import EnterpriseMatcher
from app.tools.analysis.trajectory_source_analysis.visualization_generator import VisualizationGenerator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class TrajectorySourceAnalysisTool(LLMTool):
    """
    轨迹+源清单分析工具
    
    基于HYSPLIT轨迹追踪气团真实传输路径，
    结合企业源清单识别潜在贡献源。
    
    相比传统上风向分析，本工具：
    - 考虑风向变化和气团绕流
    - 追踪1-3天的完整传输历史
    - 科学性更强，结果更可靠
    
    版本：1.0.0
    """
    
    def __init__(self):
        function_schema = {
            "name": "analyze_trajectory_sources",
            "description": """
轨迹+源清单分析工具 - 基于HYSPLIT轨迹的科学溯源

功能：
1. **后向溯源(backward)**：分析过去1-3天，识别"谁可能造成了当前污染"
2. **前向预测(forward)**：预测未来1-3天，给出"需要管控哪些企业"的建议

相比传统上风向分析的优势：
- 追踪气团真实三维传输路径（非简化直线）
- 考虑风向变化、气团抬升/下沉
- 时间覆盖1-3天（非瞬时风向）
- 科学性更强，适合深度分析和决策支持

输出：
- 企业贡献排名（Top 15）
- 轨迹密度热力图
- 行业分布分析
- 管控建议

注意：
- 分析耗时约3-5分钟（需要运行多条HYSPLIT轨迹）
- 依赖NOAA HYSPLIT服务和企业源清单API
- 建议在重要污染事件或决策场景使用
""".strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "分析点纬度（如广州：23.13）"
                    },
                    "lon": {
                        "type": "number",
                        "description": "分析点经度（如广州：113.26）"
                    },
                    "city_name": {
                        "type": "string",
                        "description": "城市名称（可选，用于结果展示）"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["backward", "forward"],
                        "default": "backward",
                        "description": "分析模式：backward=溯源（分析过去），forward=预测（分析未来）"
                    },
                    "days": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 3,
                        "description": "分析天数（1-3天，默认2天）"
                    },
                    "pollutant": {
                        "type": "string",
                        "enum": ["VOCs", "NOx", "SO2", "PM2.5", "PM10", "CO"],
                        "default": "VOCs",
                        "description": "关注的污染物类型"
                    },
                    "search_radius_km": {
                        "type": "number",
                        "default": 5,
                        "description": "轨迹点周边企业搜索半径（公里，默认5）"
                    },
                    "top_n": {
                        "type": "integer",
                        "default": 15,
                        "description": "返回贡献排名前N的企业（默认15）"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
        
        super().__init__(
            name="analyze_trajectory_sources",
            description="Trajectory-based source analysis using HYSPLIT and emission inventory",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )
        
        self.trajectory_runner = TrajectoryRunner(max_concurrent=3)
        self.enterprise_matcher = EnterpriseMatcher()
        self.visualization_generator = VisualizationGenerator()
    
    async def execute(
        self,
        context: "ExecutionContext",
        lat: float,
        lon: float,
        city_name: str = None,
        mode: str = "backward",
        days: int = 2,
        pollutant: str = "VOCs",
        search_radius_km: float = 5.0,
        top_n: int = 15,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行轨迹源清单分析
        
        Args:
            context: 执行上下文
            lat: 分析点纬度
            lon: 分析点经度
            city_name: 城市名称
            mode: 分析模式 (backward/forward)
            days: 分析天数
            pollutant: 关注的污染物
            search_radius_km: 搜索半径
            top_n: 返回企业数量
        
        Returns:
            UDF v2.0格式的分析结果
        """
        try:
            logger.info(
                "trajectory_source_analysis_start",
                lat=lat,
                lon=lon,
                mode=mode,
                days=days,
                pollutant=pollutant,
                session_id=context.session_id if context else None
            )
            
            # 参数验证
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return self._error_result("无效的经纬度坐标")
            
            if mode not in ["backward", "forward"]:
                mode = "backward"
            
            days = max(1, min(3, days))
            
            # Step 1: 运行轨迹
            trajectory_result = await self.trajectory_runner.run_analysis_trajectories(
                lat=lat,
                lon=lon,
                mode=mode,
                days=days,
                time_interval_hours=6  # 每6小时一条轨迹
            )
            
            if not trajectory_result.get("success"):
                return self._error_result(
                    f"轨迹计算失败: {trajectory_result.get('summary', {})}"
                )
            
            endpoints = trajectory_result.get("endpoints", [])
            
            if not endpoints:
                return self._error_result("未获取到有效轨迹数据")
            
            # Step 2: 企业匹配
            self.enterprise_matcher.search_radius_km = search_radius_km
            
            contributions = await self.enterprise_matcher.match_trajectories_to_enterprises(
                endpoints=endpoints,
                pollutant=pollutant
            )
            
            # Step 3: 排名
            top_contributors = self.enterprise_matcher.rank_contributions(
                contributions=contributions,
                top_n=top_n
            )
            
            # Step 4: 生成可视化
            target_location = {"lat": lat, "lon": lon}
            
            visuals = self.visualization_generator.generate_all_visuals(
                endpoints=endpoints,
                top_contributors=top_contributors,
                target_location=target_location,
                mode=mode,
                pollutant=pollutant
            )
            
            # Step 5: 生成建议
            trajectory_summary = {
                "total_trajectories": trajectory_result.get("summary", {}).get("successful", 0),
                "total_endpoints": len(endpoints),
                "enterprises_matched": len(contributions)
            }
            
            recommendations = self.visualization_generator.generate_recommendations(
                top_contributors=top_contributors,
                trajectory_summary=trajectory_summary,
                mode=mode,
                pollutant=pollutant
            )
            
            # Step 6: 汇总排放信息
            emission_summary = self._calculate_emission_summary(top_contributors, pollutant)
            
            # 计算分析时间段
            now = datetime.utcnow()
            if mode == "backward":
                analysis_period = {
                    "start": (now - timedelta(days=days+1)).isoformat() + "Z",
                    "end": (now - timedelta(days=1)).isoformat() + "Z",
                    "days": days
                }
            else:
                analysis_period = {
                    "start": (now - timedelta(days=1)).isoformat() + "Z",
                    "end": (now - timedelta(days=1) + timedelta(days=days)).isoformat() + "Z",
                    "days": days
                }
            
            logger.info(
                "trajectory_source_analysis_complete",
                mode=mode,
                total_endpoints=len(endpoints),
                matched_enterprises=len(contributions),
                top_contributors=len(top_contributors)
            )

            result_payload = {
                "status": "success",
                "success": True,
                "mode": mode,
                "analysis_period": analysis_period,
                "target_location": {
                    "lat": lat,
                    "lon": lon,
                    "city": city_name or "未指定"
                },
                "pollutant": pollutant,
                "top_contributors": top_contributors,
                "trajectory_summary": {
                    "total_trajectories": trajectory_result.get("summary", {}).get("successful", 0),
                    "total_endpoints": len(endpoints),
                    "valid_endpoints": sum(1 for ep in endpoints if ep.get("height", 0) <= 1500),
                    "enterprises_matched": len(contributions),
                    "noaa_job_ids": [
                        j.get("job_id") for j in trajectory_result.get("successful_jobs", [])
                        if j.get("job_id")
                    ]
                },
                "emission_summary": emission_summary,
                "visuals": visuals,
                "recommendations": recommendations,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "analyze_trajectory_sources",
                    "generator_version": "1.0.0",
                    "field_mapping_applied": True,
                    "computation_params": {
                        "search_radius_km": search_radius_km,
                        "interpolation_interval_km": self.enterprise_matcher.interpolation_interval_km,
                        "max_height_m": self.enterprise_matcher.max_height_m
                    }
                },
            }

            # 兼容旧字段结构，便于前端一次性读取
            result_payload["data"] = {
                "top_contributors": top_contributors,
                "trajectory_summary": result_payload["trajectory_summary"],
                "emission_summary": emission_summary
            }

            result_payload["summary"] = (
                    f"[OK] {'后向溯源' if mode == 'backward' else '前向预测'}分析完成，已保存为 {data_id}。"
                    f"分析{days}天轨迹，识别{len(contributions)}家企业，"
                    f"Top1: {top_contributors[0]['enterprise_name'] if top_contributors else 'N/A'} "
                    f"({top_contributors[0]['contribution_percent'] if top_contributors else '0%'})"
                )

            data_id = None
            try:
                data_id = context.save_data(
                    data=[result_payload],
                    schema="trajectory_analysis_result",
                    metadata={
                        "mode": mode,
                        "pollutant": pollutant,
                        "city": city_name or "未指定",
                        "lat": lat,
                        "lon": lon,
                        "days": days
                    }
                )
                result_payload["data_id"] = data_id
                result_payload["registry_schema"] = "trajectory_analysis_result"
                logger.info(
                    "trajectory_source_result_saved",
                    data_id=data_id,
                    schema="trajectory_analysis_result"
                )
            except Exception as save_error:
                logger.warning(
                    "trajectory_source_result_save_failed",
                    error=str(save_error)
                )

            return result_payload
            
        except Exception as e:
            logger.error(
                "trajectory_source_analysis_error",
                lat=lat,
                lon=lon,
                error=str(e),
                exc_info=True
            )
            return self._error_result(str(e))
    
    def _calculate_emission_summary(
        self,
        top_contributors: List[Dict[str, Any]],
        pollutant: str
    ) -> Dict[str, Any]:
        """计算排放汇总"""
        total_emission = 0
        industry_emissions = {}
        
        for ent in top_contributors:
            emission_info = ent.get("emission_info", {})
            emission = emission_info.get(pollutant, 0)
            total_emission += emission
            
            industry = ent.get("industry", "未知")
            if industry not in industry_emissions:
                industry_emissions[industry] = {"count": 0, "total": 0}
            industry_emissions[industry]["count"] += 1
            industry_emissions[industry]["total"] += emission
        
        # 按排放量排序行业
        top_industries = sorted(
            [
                {"industry": ind, "count": data["count"], f"total_{pollutant}": round(data["total"], 3)}
                for ind, data in industry_emissions.items()
            ],
            key=lambda x: x[f"total_{pollutant}"],
            reverse=True
        )[:5]
        
        return {
            f"total_matched_{pollutant}": round(total_emission, 3),
            "top_industries": top_industries
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """生成错误结果"""
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "visuals": [],
            "recommendations": [],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "analyze_trajectory_sources",
                "error": error_msg
            },
            "summary": f"轨迹源清单分析失败: {error_msg}"
        }
