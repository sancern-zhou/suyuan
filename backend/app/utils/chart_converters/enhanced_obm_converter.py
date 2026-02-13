"""
Enhanced OBM结果图表数据转换器 - UDF v2.0 + Chart v3.1

将增强OBM（EKMA/PO3/RIR）分析结果转换为标准图表格式。
支持等值线图、时序图、柱状图、热力图等多种可视化类型。

版本：v1.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class EnhancedOBMChartConverter:
    """增强OBM结果图表数据转换器

    专门负责将EKMA、PO3、RIR三大引擎的分析结果转换为各种图表格式
    """

    # ============================================
    # 主入口
    # ============================================

    @staticmethod
    def convert_to_charts(
        enhanced_obm_result: Dict[str, Any],
        chart_types: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """将增强OBM结果转换为多个图表

        Args:
            enhanced_obm_result: 增强OBM分析结果
            chart_types: 指定图表类型列表，None则自动生成所有适用图表
            **kwargs: 额外参数（meta信息等）

        Returns:
            图表数据列表（Chart v3.1格式）
        """
        logger.info(
            "enhanced_obm_conversion_start",
            has_ekma="ekma" in enhanced_obm_result.get("results", {}),
            has_po3="po3" in enhanced_obm_result.get("results", {}),
            has_rir="rir" in enhanced_obm_result.get("results", {}),
        )

        charts = []
        results = enhanced_obm_result.get("results", enhanced_obm_result)
        station_name = enhanced_obm_result.get("station_name", "未知站点")

        # EKMA图表
        if "ekma" in results and results["ekma"]:
            ekma_charts = EnhancedOBMChartConverter._generate_ekma_charts(
                results["ekma"], station_name, **kwargs
            )
            charts.extend(ekma_charts)

        # PO3图表
        if "po3" in results and results["po3"]:
            po3_charts = EnhancedOBMChartConverter._generate_po3_charts(
                results["po3"], station_name, **kwargs
            )
            charts.extend(po3_charts)

        # RIR图表
        if "rir" in results and results["rir"]:
            rir_charts = EnhancedOBMChartConverter._generate_rir_charts(
                results["rir"], station_name, **kwargs
            )
            charts.extend(rir_charts)

        logger.info(
            "enhanced_obm_conversion_complete",
            total_charts=len(charts)
        )

        return charts

    # ============================================
    # EKMA图表生成
    # ============================================

    @staticmethod
    def _generate_ekma_charts(
        ekma_data: Dict[str, Any],
        station_name: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """生成EKMA敏感性分析图表

        推荐图表类型：
        1. 等值线/热力图 - 显示VOC/NOx控制效率网格
        2. 饼图 - 敏感性类型分布
        3. 柱状图 - 控制效率对比
        """
        charts = []

        sensitivity_type = ekma_data.get("sensitivity_type", "unknown")
        control_recommendation = ekma_data.get("control_recommendation", "")
        base_o3 = ekma_data.get("base_o3", 0)

        # 1. EKMA敏感性热力图
        if "po3" in ekma_data and "voc_factor" in ekma_data and "nox_factor" in ekma_data:
            # 转换为ChartPanel期望的heatmap格式: {xAxis, yAxis, data: [[x,y,value]...]}
            voc_factors = ekma_data.get("voc_factor", [])[:20]
            nox_factors = ekma_data.get("nox_factor", [])[:20]
            po3_values = ekma_data.get("po3", [])
            
            # 构建[[x_index, y_index, value], ...] 格式
            heatmap_data = []
            for i, voc in enumerate(voc_factors):
                for j, nox in enumerate(nox_factors):
                    idx = i * len(nox_factors) + j
                    if idx < len(po3_values):
                        heatmap_data.append([i, j, po3_values[idx]])
            
            heatmap_chart = {
                "id": f"ekma_sensitivity_heatmap_{station_name}",
                "type": "heatmap",
                "title": f"{station_name} EKMA敏感性等值线图",
                "data": {
                    "xAxis": [f"{v:.2f}" for v in voc_factors],
                    "yAxis": [f"{n:.2f}" for n in nox_factors],
                    "data": heatmap_data
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "ekma_sensitivity",
                    "sensitivity_type": sensitivity_type,
                    "base_o3": base_o3,
                    "layout_hint": "wide",
                    "xLabel": "VOC减排因子",
                    "yLabel": "NOx减排因子",
                    "unit": "ppb/h"
                }
            }
            charts.append(heatmap_chart)

        # 2. EKMA敏感性类型指示图（仪表盘/饼图）
        sensitivity_chart = {
            "id": f"ekma_sensitivity_type_{station_name}",
            "type": "pie",
            "title": f"{station_name} O3敏感性类型诊断",
            "data": EnhancedOBMChartConverter._get_sensitivity_pie_data(sensitivity_type),
            "meta": {
                "schema_version": "3.1",
                "generator": "EnhancedOBMChartConverter",
                "scenario": "ekma_sensitivity_type",
                "sensitivity_type": sensitivity_type,
                "control_recommendation": control_recommendation,
                "base_o3": base_o3,
                "layout_hint": "side"
            }
        }
        charts.append(sensitivity_chart)

        # 3. 控制效率对比柱状图
        control_chart = {
            "id": f"ekma_control_comparison_{station_name}",
            "type": "bar",
            "title": f"{station_name} VOCs/NOx控制效率对比",
            "data": {
                "x": ["VOCs控制", "NOx控制"],
                "y": EnhancedOBMChartConverter._calculate_control_effectiveness(sensitivity_type)
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "EnhancedOBMChartConverter",
                "scenario": "ekma_control_comparison",
                "unit": "%",
                "control_recommendation": control_recommendation,
                "layout_hint": "side"
            }
        }
        charts.append(control_chart)

        return charts

    @staticmethod
    def _get_sensitivity_pie_data(sensitivity_type: str) -> List[Dict[str, Any]]:
        """根据敏感性类型生成饼图数据"""
        if sensitivity_type == "VOCs-limited":
            return [
                {"name": "VOCs敏感", "value": 80},
                {"name": "NOx敏感", "value": 20}
            ]
        elif sensitivity_type == "NOx-limited":
            return [
                {"name": "VOCs敏感", "value": 20},
                {"name": "NOx敏感", "value": 80}
            ]
        else:  # transitional
            return [
                {"name": "VOCs敏感", "value": 50},
                {"name": "NOx敏感", "value": 50}
            ]

    @staticmethod
    def _calculate_control_effectiveness(sensitivity_type: str) -> List[float]:
        """根据敏感性类型计算控制效率"""
        if sensitivity_type == "VOCs-limited":
            return [85.0, 15.0]
        elif sensitivity_type == "NOx-limited":
            return [15.0, 85.0]
        else:  # transitional
            return [50.0, 50.0]

    # ============================================
    # PO3图表生成
    # ============================================

    @staticmethod
    def _generate_po3_charts(
        po3_data: Dict[str, Any],
        station_name: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """生成PO3时序分析图表

        推荐图表类型：
        1. 时序图 - PO3日变化曲线
        2. 柱状图 - 各时段PO3贡献
        3. 组合图 - PO3 + O3浓度对比
        """
        charts = []

        timeseries = po3_data.get("timeseries", [])
        daily_peak = po3_data.get("daily_peak", {})
        photochemical_period = po3_data.get("photochemical_period", {})
        statistics = po3_data.get("statistics", {})

        # 1. PO3时序曲线图
        if timeseries:
            times = [point.get("time", "")[-8:-3] for point in timeseries]  # HH:MM
            po3_values = [point.get("PO3_ppb_per_h", 0) for point in timeseries]
            o3_values = [point.get("O3_ppb", 0) for point in timeseries]
            trans_values = [point.get("TransO3_ppb_per_h", 0) for point in timeseries]

            timeseries_chart = {
                "id": f"po3_timeseries_{station_name}",
                "type": "timeseries",
                "title": f"{station_name} 臭氧生成速率(PO3)日变化",
                "data": {
                    "x": times,
                    "series": [
                        {"name": "PO3 (ppb/h)", "data": po3_values},
                        {"name": "O3 (ppb)", "data": o3_values},
                        {"name": "传输项 (ppb/h)", "data": trans_values}
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "po3_timeseries",
                    "peak_time": daily_peak.get("time", ""),
                    "peak_rate": daily_peak.get("po3_rate", 0),
                    "photochemical_start": photochemical_period.get("start", ""),
                    "photochemical_end": photochemical_period.get("end", ""),
                    "layout_hint": "wide"
                }
            }
            charts.append(timeseries_chart)

        # 2. PO3日峰值统计
        if statistics:
            stats_chart = {
                "id": f"po3_statistics_{station_name}",
                "type": "bar",
                "title": f"{station_name} PO3统计特征",
                "data": {
                    "x": ["平均值", "最大值", "最小值", "总生成量"],
                    "y": [
                        round(statistics.get("mean_po3", 0), 2),
                        round(statistics.get("max_po3", 0), 2),
                        round(statistics.get("min_po3", 0), 2),
                        round(statistics.get("total_ozone_production", 0), 2)
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "po3_statistics",
                    "unit": "ppb/h (总量为ppb)",
                    "data_points": statistics.get("data_points", 0),
                    "layout_hint": "side"
                }
            }
            charts.append(stats_chart)

        # 3. 光化学活跃期可视化
        if photochemical_period:
            period_chart = {
                "id": f"po3_photochemical_period_{station_name}",
                "type": "bar",
                "title": f"{station_name} 光化学活跃期",
                "data": {
                    "x": ["活跃期时长(h)", "峰值PO3(ppb/h)", "峰值O3(ppb)"],
                    "y": [
                        photochemical_period.get("peak_hours", 0),
                        daily_peak.get("po3_rate", 0),
                        daily_peak.get("o3_concentration", 0)
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "po3_photochemical",
                    "period_start": photochemical_period.get("start", ""),
                    "period_end": photochemical_period.get("end", ""),
                    "layout_hint": "side"
                }
            }
            charts.append(period_chart)

        return charts

    # ============================================
    # RIR图表生成
    # ============================================

    @staticmethod
    def _generate_rir_charts(
        rir_data: Dict[str, Any],
        station_name: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """生成RIR反应性分析图表

        推荐图表类型：
        1. 柱状图 - 关键控制物种RIR值排序
        2. 饼图 - VOC类别RIR贡献
        3. 雷达图 - 多维度物种反应性对比
        """
        charts = []

        rir_by_species = rir_data.get("rir_by_species", {})
        rir_by_category = rir_data.get("rir_by_category", {})
        key_control_species = rir_data.get("key_control_species", [])
        summary_stats = rir_data.get("summary_stats", {})

        # 1. 关键控制物种RIR柱状图（Top 10）
        if key_control_species:
            top_species = key_control_species[:10]
            species_chart = {
                "id": f"rir_key_species_{station_name}",
                "type": "bar",
                "title": f"{station_name} 关键控制VOCs物种(RIR Top 10)",
                "data": {
                    "x": [s.get("species", "") for s in top_species],
                    "y": [round(s.get("rir", 0), 6) for s in top_species]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "rir_key_species",
                    "unit": "无量纲",
                    "total_species": len(key_control_species),
                    "positive_count": summary_stats.get("positive_rir_count", 0),
                    "layout_hint": "wide"
                }
            }
            charts.append(species_chart)

        # 2. VOC类别RIR贡献饼图
        if rir_by_category:
            # 过滤正值
            positive_categories = {k: v for k, v in rir_by_category.items() if v > 0}
            if positive_categories:
                category_chart = {
                    "id": f"rir_category_{station_name}",
                    "type": "pie",
                    "title": f"{station_name} VOC类别RIR贡献分布",
                    "data": [
                        {"name": cat, "value": round(val, 4)}
                        for cat, val in positive_categories.items()
                    ],
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "EnhancedOBMChartConverter",
                        "scenario": "rir_category",
                        "total_categories": len(rir_by_category),
                        "layout_hint": "side"
                    }
                }
                charts.append(category_chart)

        # 3. RIR统计概览
        if summary_stats:
            stats_chart = {
                "id": f"rir_summary_{station_name}",
                "type": "bar",
                "title": f"{station_name} RIR统计概览",
                "data": {
                    "x": ["正效应物种", "负效应物种", "最大RIR×1000", "平均RIR×1000"],
                    "y": [
                        summary_stats.get("positive_rir_count", 0),
                        summary_stats.get("negative_rir_count", 0),
                        round(summary_stats.get("max_rir", 0) * 1000, 2),
                        round(summary_stats.get("mean_rir", 0) * 1000, 2)
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "rir_summary",
                    "max_rir": summary_stats.get("max_rir", 0),
                    "min_rir": summary_stats.get("min_rir", 0),
                    "layout_hint": "side"
                }
            }
            charts.append(stats_chart)

        # 4. 物种详细信息表格（用于前端展示）
        if key_control_species:
            table_chart = {
                "id": f"rir_species_table_{station_name}",
                "type": "table",
                "title": f"{station_name} VOCs物种RIR详细列表",
                "data": {
                    "type": "table",
                    "columns": ["优先级", "物种", "类别", "浓度(ppb)", "MIR系数", "RIR值"],
                    "rows": [
                        [
                            s.get("control_priority", 0),
                            s.get("species", ""),
                            s.get("category", ""),
                            round(s.get("concentration", 0), 2),
                            round(s.get("mir", 0), 2),
                            f"{s.get('rir', 0):.6f}"
                        ]
                        for s in key_control_species[:20]  # 限制20条
                    ]
                },
                "meta": {
                    "schema_version": "3.1",
                    "generator": "EnhancedOBMChartConverter",
                    "scenario": "rir_species_table",
                    "layout_hint": "wide"
                }
            }
            charts.append(table_chart)

        return charts

    # ============================================
    # 综合图表生成
    # ============================================

    @staticmethod
    def generate_summary_dashboard(
        enhanced_obm_result: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """生成增强OBM分析综合仪表盘

        Args:
            enhanced_obm_result: 完整的增强OBM分析结果

        Returns:
            包含多个图表的仪表盘配置
        """
        station_name = enhanced_obm_result.get("station_name", "未知站点")
        analysis_mode = enhanced_obm_result.get("analysis_mode", "all")

        # 生成所有图表
        all_charts = EnhancedOBMChartConverter.convert_to_charts(
            enhanced_obm_result, **kwargs
        )

        # 构建仪表盘
        dashboard = {
            "id": f"enhanced_obm_dashboard_{station_name}",
            "type": "dashboard",
            "title": f"{station_name} 增强OBM综合分析",
            "charts": all_charts,
            "layout": {
                "columns": 2,
                "rows": (len(all_charts) + 1) // 2
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "EnhancedOBMChartConverter",
                "scenario": "enhanced_obm_dashboard",
                "analysis_mode": analysis_mode,
                "total_charts": len(all_charts),
                "timestamp": enhanced_obm_result.get("timestamp", "")
            }
        }

        return dashboard
