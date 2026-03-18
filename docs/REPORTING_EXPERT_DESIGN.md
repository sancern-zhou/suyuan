# 报告专家Agent设计

## 专业能力

### 核心专长
1. **专业报告撰写**
   - 环境质量报告
   - 污染事件调查报告
   - 源解析专项报告
   - 气象条件分析报告

2. **多格式报告生成**
   - Markdown格式
   - HTML网页版
   - PDF文档
   - PowerPoint演示

3. **数据解读和解释**
   - 复杂数据的通俗化表达
   - 专业术语的解释说明
   - 不确定性信息的传达
   - 风险评估和预警

4. **可视化整合**
   - 图表与文字的协调
   - 多图表组合设计
   - 交互式图表嵌入
   - 动态数据更新

## 专业工具集成

```python
class ReportingExpert(SpecializedExpertBase):

    async def generate_comprehensive_report(
        self,
        analysis_results: Dict[str, Any],
        report_type: str = "standard"
    ) -> Dict[str, Any]:
        """生成综合分析报告"""

        # 1. 数据整合和验证
        integrated_data = await self._integrate_analysis_results(analysis_results)

        # 2. 报告结构设计
        report_structure = await self._design_report_structure(report_type)

        # 3. 内容生成
        content_sections = await self._generate_content_sections(
            integrated_data, report_structure
        )

        # 4. 可视化整合
        visualizations = await self._integrate_visualizations(
            integrated_data, content_sections
        )

        # 5. 质量检查
        quality_report = await self._perform_quality_check(content_sections, visualizations)

        return {
            "report": {
                "structure": report_structure,
                "content": content_sections,
                "visualizations": visualizations,
                "metadata": await self._generate_report_metadata(analysis_results)
            },
            "quality_assessment": quality_report,
            "export_options": await self._prepare_export_formats(content_sections, visualizations)
        }

    async def generate_pollution_event_report(
        self,
        event_data: Dict[str, Any],
        meteorology_data: Dict[str, Any] = None,
        source_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """生成污染事件专项报告"""

        # 1. 事件特征描述
        event_summary = await self._summarize_event_characteristics(event_data)

        # 2. 气象条件分析
        met_analysis = ""
        if meteorology_data:
            met_analysis = await self._interpret_meteorological_conditions(meteorology_data)

        # 3. 源贡献分析
        source_analysis = ""
        if source_data:
            source_analysis = await self._interpret_source_contributions(source_data)

        # 4. 事件成因分析
        causation_analysis = await self._analyze_event_causation(
            event_summary, met_analysis, source_analysis
        )

        # 5. 影响评估
        impact_assessment = await self._assess_environmental_impact(event_data)

        # 6. 建议措施
        recommendations = await self._generate_recommendations(
            causation_analysis, impact_assessment
        )

        return {
            "executive_summary": await self._create_executive_summary(
                event_summary, causation_analysis
            ),
            "event_description": event_summary,
            "meteorological_analysis": met_analysis,
            "source_analysis": source_analysis,
            "causation_analysis": causation_analysis,
            "impact_assessment": impact_assessment,
            "recommendations": recommendations,
            "technical_details": await self._generate_technical_appendix(event_data),
            "visualizations": await self._select_key_visualizations(event_data)
        }
```

## 专业报告模板

### 1. 环境质量分析报告

```python
class EnvironmentalQualityReportTemplate:
    """环境质量分析报告模板"""

    async def create_report(
        self,
        location: str,
        time_period: str,
        pollutant_data: Dict[str, Any],
        meteorology_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建环境质量分析报告"""

        return {
            "title": f"{location}环境质量分析报告（{time_period}）",
            "sections": {
                "1_executive_summary": {
                    "title": "摘要",
                    "content": await self._generate_executive_summary(pollutant_data),
                    "key_findings": await self._extract_key_findings(pollutant_data)
                },
                "2_methodology": {
                    "title": "监测方法与数据来源",
                    "content": await self._describe_methodology(pollutant_data)
                },
                "3_air_quality_status": {
                    "title": "空气质量状况",
                    "subsections": {
                        "3_1_overall_assessment": {
                            "title": "总体评估",
                            "content": await self._assess_overall_air_quality(pollutant_data)
                        },
                        "3_2_pollutant_analysis": {
                            "title": "主要污染物分析",
                            "content": await self._analyze_pollutants(pollutant_data)
                        },
                        "3_3_trend_analysis": {
                            "title": "变化趋势分析",
                            "content": await self._analyze_trends(pollutant_data)
                        },
                        "3_4_spatial_distribution": {
                            "title": "空间分布特征",
                            "content": await self._analyze_spatial_patterns(pollutant_data)
                        }
                    },
                    "visualizations": await self._create_air_quality_visualizations(pollutant_data)
                },
                "4_meteorological_influence": {
                    "title": "气象条件影响分析",
                    "content": await self._analyze_meteorological_influence(
                        pollutant_data, meteorology_data
                    ),
                    "visualizations": await self._create_meteorological_visualizations(
                        meteorology_data
                    )
                },
                "5_source_analysis": {
                    "title": "污染源解析",
                    "content": await self._analyze_pollution_sources(pollutant_data),
                    "visualizations": await self._create_source_visualizations(pollutant_data)
                },
                "6_health_risk_assessment": {
                    "title": "健康风险评估",
                    "content": await self._assess_health_risks(pollutant_data)
                },
                "7_conclusions_recommendations": {
                    "title": "结论与建议",
                    "content": {
                        "conclusions": await self._draw_conclusions(pollutant_data),
                        "recommendations": await self._generate_recommendations(pollutant_data)
                    }
                },
                "8_appendix": {
                    "title": "附录",
                    "content": await self._create_appendix(pollutant_data, meteorology_data)
                }
            }
        }
```

### 2. 污染事件调查报告

```python
class PollutionEventReportTemplate:
    """污染事件调查报告模板"""

    async def create_investigation_report(
        self,
        event_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建污染事件调查报告"""

        return {
            "title": f"污染事件调查报告 - {event_info['event_name']}",
            "sections": {
                "1_incident_overview": {
                    "title": "事件概况",
                    "content": await self._create_incident_overview(event_info)
                },
                "2_event_timeline": {
                    "title": "事件时间线",
                    "content": await self._create_event_timeline(event_info),
                    "visualization": await self._create_timeline_chart(event_info)
                },
                "3_pollution_characteristics": {
                    "title": "污染特征",
                    "subsections": {
                        "3_1_concentration_levels": {
                            "title": "浓度水平",
                            "content": await self._describe_concentration_levels(event_info)
                        },
                        "3_2_chemical_composition": {
                            "title": "化学组分",
                            "content": await self._describe_chemical_composition(event_info)
                        },
                        "3_3_spatial_extent": {
                            "title": "空间范围",
                            "content": await self._describe_spatial_extent(event_info)
                        }
                    },
                    "visualizations": await self._create_pollution_visualizations(event_info)
                },
                "4_meteorological_analysis": {
                    "title": "气象条件分析",
                    "content": await self._analyze_event_meteorology(event_info),
                    "visualizations": await self._create_meteorological_visualizations(event_info)
                },
                "5_source_investigation": {
                    "title": "污染源调查",
                    "content": await self._investigate_pollution_sources(event_info)
                },
                "6_impact_assessment": {
                    "title": "环境影响评估",
                    "content": await self._assess_environmental_impacts(event_info)
                },
                "7_root_cause_analysis": {
                    "title": "成因分析",
                    "content": await self._analyze_root_causes(event_info)
                },
                "8_response_actions": {
                    "title": "应对措施",
                    "content": await self._document_response_actions(event_info)
                },
                "9_lessons_learned": {
                    "title": "经验教训",
                    "content": await self._summarize_lessons_learned(event_info)
                },
                "10_prevention_recommendations": {
                    "title": "预防建议",
                    "content": await self._generate_prevention_recommendations(event_info)
                }
            }
        }
```

## 智能内容生成

### 1. 数据解读系统

```python
class IntelligentDataInterpreter:
    """智能数据解读系统"""

    async def interpret_pollution_data(
        self,
        data: Dict[str, Any],
        interpretation_type: str
    ) -> Dict[str, Any]:
        """智能解读污染数据"""

        # 1. 异常检测
        anomalies = await self._detect_anomalies(data)

        # 2. 趋势识别
        trends = await self._identify_trends(data)

        # 3. 相关性分析
        correlations = await self._analyze_correlations(data)

        # 4. 解读生成
        interpretation = await self._generate_interpretation(
            anomalies, trends, correlations, interpretation_type
        )

        return {
            "summary": await self._create_summary(anomalies, trends),
            "detailed_analysis": interpretation,
            "key_insights": await self._extract_key_insights(interpretation),
            "supporting_evidence": await self._provide_evidence(correlations)
        }

    async def generate_narrative(
        self,
        data_analysis: Dict[str, Any],
        narrative_style: str = "professional"
    ) -> str:
        """生成数据叙述"""

        narrative_templates = {
            "professional": "专业的技术报告风格",
            "accessible": "通俗易懂的公众报告风格",
            "executive": "面向决策者的简明风格"
        }

        template = narrative_templates.get(narrative_style, narrative_templates["professional"])

        return await self._apply_narrative_template(template, data_analysis)
```

### 2. 建议生成系统

```python
class RecommendationGenerator:
    """建议生成系统"""

    async def generate_recommendations(
        self,
        analysis_results: Dict[str, Any],
        target_audience: str = "policy_makers"
    ) -> Dict[str, Any]:
        """生成针对性建议"""

        # 1. 问题识别
        problems = await self._identify_key_problems(analysis_results)

        # 2. 解决方案检索
        solutions = await self._retrieve_solutions(problems)

        # 3. 可行性评估
        feasibility = await self._assess_feasibility(solutions)

        # 4. 优先级排序
        prioritized_recommendations = await self._prioritize_recommendations(
            solutions, feasibility
        )

        return {
            "immediate_actions": prioritized_recommendations["immediate"],
            "short_term_measures": prioritized_recommendations["short_term"],
            "long_term_strategies": prioritized_recommendations["long_term"],
            "implementation_plan": await self._create_implementation_plan(
                prioritized_recommendations
            ),
            "expected_outcomes": await self._predict_outcomes(prioritized_recommendations)
        }
```

## 协作策略

### 与其他专家协作

#### 气象专家协作
- **数据整合**：整合气象分析结果
- **专业解读**：提供气象条件的专业解释
- **风险评估**：基于气象条件评估污染风险

#### 环境组分专家协作
- **源解析结果**：整合PMF/OBM分析结果
- **健康风险**：基于污染物组分评估健康风险
- **控制建议**：针对主要污染源提出控制建议

#### 可视化专家协作
- **图表需求**：提出报告所需的图表类型
- **版式设计**：设计报告的整体版式
- **可视化质量**：确保图表的专业性和美观性

## 质量保证

### 1. 内容质量检查

```python
async def validate_report_quality(self, report: Dict[str, Any]) -> Dict[str, Any]:
    """验证报告质量"""

    quality_checks = {
        "content_accuracy": await self._check_content_accuracy(report),
        "logical_consistency": await self._check_logical_consistency(report),
        "completeness": await self._assess_completeness(report),
        "clarity": await self._assess_clarity(report),
        "technical_accuracy": await self._verify_technical_accuracy(report),
        "visualization_quality": await self._evaluate_visualization_quality(report)
    }

    overall_score = sum(score["score"] for score in quality_checks.values()) / len(quality_checks)

    return {
        "quality_score": overall_score,
        "quality_details": quality_checks,
        "improvement_suggestions": await self._generate_improvement_suggestions(quality_checks),
        "compliance_check": await self._check_report_compliance(report)
    }
```

### 2. 多语言支持

```python
async def translate_report(self, report: Dict[str, Any], target_language: str) -> Dict[str, Any]:
    """报告多语言翻译"""

    translation_engine = await self._get_translation_engine()

    # 保持专业术语的准确性
    translated_report = await translation_engine.translate_with_terminology(
        report, target_language
    )

    # 调整文化适应性
    culturally_adapted_report = await self._adapt_to_culture(
        translated_report, target_language
    )

    return culturally_adapted_report
```

## 性能指标

- **报告生成速度**: <30秒（综合报告）
- **内容准确率**: >95%
- **用户满意度**: >90%
- **格式兼容性**: 支持10+种导出格式
- **可读性得分**: >8/10

## 持续优化

- **模板库扩展**：不断积累高质量报告模板
- **语言模型优化**：基于用户反馈优化内容生成
- **知识库更新**：定期更新专业知识和最佳实践
- **自动化程度提升**：提高报告生成的自动化水平
