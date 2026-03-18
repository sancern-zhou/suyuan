# 数据可视化专家Agent设计

## 专业能力

### 核心专长
1. **专业图表设计**
   - 科学可视化标准（SciVis）
   - 气象数据专用图表（风玫瑰图、剖面图、轨迹图）
   - 环境数据可视化（时间序列、热力图、桑基图）
   - 多维数据降维可视化

2. **交互式分析**
   - 动态图表生成
   - 多尺度数据探索
   - 实时数据更新
   - 用户交互优化

3. **视觉感知优化**
   - 色彩理论应用
   - 视觉层次设计
   - 认知负荷优化
   - 可访问性设计

4. **多平台适配**
   - Web端可视化（ECharts、D3.js）
   - 移动端优化
   - 报告生成（PDF、SVG）
   - 数据仪表板

## 专业工具集成

```python
class VisualizationExpert(SpecializedExpertBase):

    async def create_professional_visualization(
        self,
        data: Dict[str, Any],
        visualization_type: str,
        context: str = "analysis"
    ) -> Dict[str, Any]:
        """创建专业可视化"""

        # 1. 数据预处理
        processed_data = await self._preprocess_data(data, visualization_type)

        # 2. 图表设计
        chart_config = await self._design_chart_config(visualization_type, context)

        # 3. 视觉映射
        visual_mapping = self._create_visual_mapping(processed_data, chart_config)

        # 4. 交互设计
        interactions = await self._design_interactions(visualization_type, context)

        # 5. 响应式布局
        layout = await self._create_responsive_layout(visualization_type)

        return {
            "chart_config": {
                "type": visualization_type,
                "data": visual_mapping,
                "layout": layout,
                "interactions": interactions,
                "styling": await self._generate_professional_styling(visualization_type)
            },
            "metadata": {
                "visualization_id": str(uuid.uuid4()),
                "created_at": datetime.utcnow().isoformat(),
                "context": context,
                "data_source": data.get("source", "unknown"),
                "quality_score": self._assess_visualization_quality(visual_mapping)
            }
        }

    async def create_meteorological_visualization(
        self,
        meteorology_data: Dict[str, Any],
        chart_type: str
    ) -> Dict[str, Any]:
        """气象数据专用可视化"""

        if chart_type == "wind_rose":
            return await self._create_wind_rose(meteorology_data)
        elif chart_type == "trajectory_map":
            return await self._create_trajectory_map(meteorology_data)
        elif chart_type == "boundary_layer_profile":
            return await self._create_boundary_layer_profile(meteorology_data)
        elif chart_type == "synoptic_chart":
            return await self._create_synoptic_chart(meteorology_data)

    async def create_components_visualization(
        self,
        composition_data: Dict[str, Any],
        chart_type: str
    ) -> Dict[str, Any]:
        """组分数据专用可视化"""

        if chart_type == "pmf_results":
            return await self._create_pmf_stacked_bar(composition_data)
        elif chart_type == "source_contribution":
            return await self._create_source_sankey(composition_data)
        elif chart_type == "chemical_fingerprint":
            return await self._create_fingerprint_radar(composition_data)
        elif chart_type == "time_series":
            return await self._create_pollution_timeseries(composition_data)
```

## 专业图表库

### 1. 气象专用图表

```python
class MeteorologicalChartLibrary:

    async def _create_wind_rose(self, data: Dict) -> Dict[str, Any]:
        """创建风玫瑰图"""
        return {
            "type": "wind_rose",
            "title": "风向玫瑰图",
            "data": {
                "sectors": self._calculate_wind_sectors(data["wind_direction"]),
                "series": [{
                    "name": "风速频率",
                    "data": self._calculate_wind_speed_distribution(data)
                }]
            },
            "config": {
                "coordinate_system": "polar",
                "radius_axis": {"max": 20},
                "angle_axis": {
                    "type": "category",
                    "data": ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
                },
                "legend": {"show": True}
            }
        }

    async def _create_trajectory_map(self, trajectory_data: Dict) -> Dict[str, Any]:
        """创建轨迹地图"""
        return {
            "type": "map",
            "title": "污染物传输轨迹",
            "data": {
                "map_center": trajectory_data.get("center"),
                "zoom": 6,
                "layers": [
                    {
                        "type": "trajectory_layer",
                        "trajectories": self._format_trajectory_paths(trajectory_data),
                        "style": {
                            "strokeColor": "#FF6B6B",
                            "strokeWeight": 3,
                            "strokeOpacity": 0.8
                        }
                    },
                    {
                        "type": "source_marker",
                        "data": trajectory_data.get("sources", [])
                    }
                ]
            }
        }

    async def _create_synoptic_chart(self, met_data: Dict) -> Dict[str, Any]:
        """创建天气形势图"""
        return {
            "type": "synoptic",
            "title": "天气形势分析",
            "data": {
                "pressure_contours": self._generate_pressure_contours(met_data["pressure"]),
                "fronts": self._identify_fronts(met_data),
                "systems": self._locate_systems(met_data),
                "wind_vectors": self._create_wind_vectors(met_data["wind"])
            }
        }
```

### 2. 环境组分专用图表

```python
class ComponentsChartLibrary:

    async def _create_pmf_stacked_bar(self, pmf_data: Dict) -> Dict[str, Any]:
        """创建PMF因子贡献堆叠图"""
        return {
            "type": "stacked_bar",
            "title": "PMF源贡献分析",
            "data": {
                "x": pmf_data["time_axis"],
                "series": [
                    {
                        "name": source["name"],
                        "data": source["contribution"],
                        "stack": "source",
                        "itemStyle": {"color": source["color"]}
                    }
                    for source in pmf_data["sources"]
                ]
            },
            "config": {
                "tooltip": {
                    "trigger": "axis",
                    "axisPointer": {"type": "shadow"},
                    "formatter": self._format_pmf_tooltip
                },
                "legend": {"top": 20}
            }
        }

    async def _create_source_sankey(self, source_data: Dict) -> Dict[str, Any]:
        """创建源贡献桑基图"""
        return {
            "type": "sankey",
            "title": "污染源贡献流",
            "data": {
                "nodes": self._format_sankey_nodes(source_data),
                "links": self._format_sankey_links(source_data)
            },
            "config": {
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {
                    "color": "gradient",
                    "curveness": 0.5
                }
            }
        }

    async def _create_fingerprint_radar(self, fingerprint_data: Dict) -> Dict[str, Any]:
        """创建化学指纹雷达图"""
        return {
            "type": "radar",
            "title": "污染物化学指纹",
            "data": {
                "indicators": [
                    {"name": compound, "max": 100}
                    for compound in fingerprint_data["compounds"]
                ],
                "series": [
                    {
                        "name": "样品",
                        "data": [fingerprint_data["values"]],
                        "areaStyle": {"opacity": 0.3}
                    }
                ]
            },
            "config": {
                "radar": {
                    "indicator": self._format_radar_indicators(fingerprint_data),
                    "splitArea": {"show": True}
                }
            }
        }
```

## 协作策略

### 与气象专家协作
- **需求理解**：深入理解气象数据特点和可视化需求
- **专业图表**：实现气象专用图表（风玫瑰、剖面图等）
- **数据标注**：提供专业的图表解读标注

### 与环境组分专家协作
- **源解析可视化**：设计PMF结果的专业展示
- **组分分析图**：创建化学指纹、源贡献等专用图表
- **数据验证**：通过可视化验证分析结果

### 与报告专家协作
- **报告配图**：生成高质量的报告配图
- **多格式输出**：支持PDF、SVG、PNG等多格式导出
- **版式设计**：设计符合报告规范的图表布局

## 智能设计系统

```python
class IntelligentVisualizationDesigner:
    """智能可视化设计系统"""

    async def auto_design(self, data: Dict[str, Any], context: str) -> Dict[str, Any]:
        """自动设计最佳可视化方案"""

        # 1. 数据特征分析
        data_features = await self._analyze_data_features(data)

        # 2. 任务理解
        task_context = await self._understand_task_context(context)

        # 3. 图表类型推荐
        recommended_charts = await self._recommend_chart_types(
            data_features, task_context
        )

        # 4. 设计方案生成
       设计方案 = await self._generate_design_scheme(
            data, recommended_charts, task_context
        )

        return {
            "recommended_chart": recommended_charts[0],
            "alternative_charts": recommended_charts[1:],
            "design_rationale": await self._explain_design_choice(
                data_features, recommended_charts[0]
            ),
            "implementation": 设计方案
        }

    async def optimize_visualization(
        self,
        current_chart: Dict[str, Any],
        user_feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于用户反馈优化可视化"""

        # 分析用户反馈
        feedback_analysis = await self._analyze_feedback(user_feedback)

        # 识别优化机会
        optimization_opportunities = self._identify_optimization_opportunities(
            current_chart, feedback_analysis
        )

        # 生成优化方案
        optimized_chart = await self._apply_optimizations(
            current_chart, optimization_opportunities
        )

        return optimized_chart
```

## 质量控制

### 设计质量检查
```python
async def validate_visualization_quality(self, chart_config: Dict) -> Dict[str, Any]:
    """验证可视化质量"""

    quality_checks = {
        "data_accuracy": await self._check_data_accuracy(chart_config),
        "visual_clarity": await self._assess_visual_clarity(chart_config),
        "color_accessibility": await self._check_color_accessibility(chart_config),
        "performance": await self._assess_performance(chart_config),
        "interactivity": await self._evaluate_interactivity(chart_config)
    }

    overall_score = sum(
        score["score"] for score in quality_checks.values()
    ) / len(quality_checks)

    return {
        "quality_score": overall_score,
        "quality_checks": quality_checks,
        "recommendations": await self._generate_quality_recommendations(quality_checks)
    }
```

## 性能指标

- **图表生成速度**: <3秒
- **交互响应时间**: <200ms
- **数据处理效率**: 支持10万+数据点
- **用户满意度**: >90%
- **设计质量得分**: >85/100

## 持续优化

- **视觉模板库**：积累高质量可视化模板
- **用户行为分析**：分析用户对图表的使用偏好
- **新技术整合**：集成最新的可视化技术（如WebGL、GPU加速）
- **设计规范更新**：根据最佳实践更新设计规范
