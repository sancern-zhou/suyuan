# 报告生成场景实施方案

## 一、概述

### 1.1 目标

构建智能报告生成系统，支持两类核心场景：

| 场景 | 描述 | 方案 |
|------|------|------|
| **场景1** | 研究报告生成 | ReAct Agent + 知识库检索 + 数据查询 + 可视化 |
| **场景2** | 模板化统计报告 | 临时报告用方案B（结构化拆解），固定报告用方案C（模板标注） |

### 1.2 核心能力

- 基于用户输入自动规划报告结构
- 知识库检索获取背景资料
- 数据查询工具获取统计数据
- LLM生成分析结论
- Markdown格式输出，支持Word导出

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端交互层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 报告生成入口 │  │ 模板上传/管理│  │ 报告预览/编辑/导出      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       报告生成服务层                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  ReportGenerationAgent                   │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────────┐    │    │
│  │  │ 规划模块  │→ │ 执行模块  │→ │ 观察/重规划模块   │    │    │
│  │  └───────────┘  └───────────┘  └───────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  TemplateReportEngine                    │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────────┐    │    │
│  │  │ 模板解析  │→ │ 数据获取  │→ │ 报告渲染          │    │    │
│  │  └───────────┘  └───────────┘  └───────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         工具层                                   │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │知识库检索   │ │数据查询    │ │可视化生成    │  │
│  │search_kb   │ │get_air_*   │ │generate_chart│  │
│  └────────────┘ └────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、场景1：研究报告生成

### 3.1 流程设计

```
用户输入研究主题
    │
    ▼
┌─────────────────────────────────────┐
│ ReportGenerationAgent               │
│                                     │
│ 1. 规划阶段 (Plan)                  │
│    - 分析用户需求                   │
│    - 确定报告结构（章节列表）        │
│    - 规划工具调用序列               │
│                                     │
│ 2. 执行阶段 (Execute)               │
│    - 知识库检索背景资料             │
│    - 数据查询获取统计数据           │
│    - 分析工具执行专业计算           │
│    - 可视化工具生成图表             │
│                                     │
│ 3. 观察阶段 (Observe)               │
│    - 检查工具返回结果               │
│    - 数据完整性验证                 │
│    - 若有问题，重新规划执行         │
│                                     │
│ 4. 生成阶段 (Generate)              │
│    - 按章节生成报告内容             │
│    - 整合图表和数据                 │
│    - 输出Markdown格式               │
└─────────────────────────────────────┘
    │
    ▼
Markdown报告 → Word导出
```

### 3.2 报告结构模板

```python
REPORT_STRUCTURE = {
    "research_report": {
        "sections": [
            {"id": "abstract", "title": "摘要", "required": True},
            {"id": "background", "title": "研究背景", "required": True, "use_knowledge_base": True},
            {"id": "methodology", "title": "研究方法", "required": True},
            {"id": "data_analysis", "title": "数据分析", "required": True, "use_data_tools": True},
            {"id": "results", "title": "研究结果", "required": True, "use_visualization": True},
            {"id": "discussion", "title": "讨论", "required": False},
            {"id": "conclusion", "title": "结论与建议", "required": True},
            {"id": "references", "title": "参考资料", "required": False, "use_knowledge_base": True}
        ]
    },
    "analysis_report": {
        "sections": [
            {"id": "summary", "title": "执行摘要", "required": True},
            {"id": "situation", "title": "现状分析", "required": True},
            {"id": "cause_analysis", "title": "原因分析", "required": True},
            {"id": "recommendations", "title": "对策建议", "required": True}
        ]
    }
}
```

### 3.3 核心组件

#### ReportGenerationAgent

```python
# backend/app/agent/report_generation_agent.py
from app.agent.context.execution_context import ExecutionContext
from app.agent.experts.expert_router_v3 import ExpertRouter

class ReportGenerationAgent:
    """研究报告生成Agent - 集成Context-Aware V2架构"""

    def __init__(self):
        self.planner = ReportPlanner()
        self.executor = ToolExecutor()  # 通过ReAct Agent工具注册表
        self.generator = SectionGenerator()
        self.expert_router = ExpertRouter()  # 集成专家路由器
        self.context = None  # ExecutionContext注入

    def set_context(self, context: ExecutionContext):
        """注入Context-Aware V2上下文"""
        self.context = context
    
    async def generate(
        self,
        topic: str,
        report_type: str = "research_report",
        requirements: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None
    ) -> AsyncGenerator[ReportEvent, None]:
        """
        生成研究报告
        
        Args:
            topic: 研究主题
            report_type: 报告类型
            requirements: 额外要求
            knowledge_base_ids: 指定知识库
            
        Yields:
            ReportEvent: 生成过程事件（进度、章节内容、图表等）
        """
        # 1. 规划阶段
        plan = await self.planner.create_plan(topic, report_type, requirements)
        yield ReportEvent(type="plan_created", data=plan)
        
        # 2. 执行阶段（按章节）
        for section in plan.sections:
            yield ReportEvent(type="section_started", data={"section_id": section.id})

            # 通过上下文管理数据（Context-Aware V2）
            if section.requires_expert:
                # 使用专家路由器调度专业专家
                result = await self.expert_router.route(
                    task=section.task,
                    expert_type=section.expert_type,
                    context=self.context
                )
            else:
                # 通过ReAct Agent工具注册表调用
                for tool_call in section.tools:
                    result = await self.executor.execute_via_context(
                        context=self.context,
                        tool_call=tool_call
                    )

                    # 观察结果（ReAct观测）
                    if not result.success:
                        # 重新规划
                        retry_plan = await self.planner.replan(section, result.error)
                        result = await self.executor.execute_via_context(
                            context=self.context,
                            tool_call=retry_plan
                        )

            yield ReportEvent(type="section_completed", data=result)
            
            # 生成章节内容
            section_content = await self.generator.generate_section(
                section=section,
                context=context,
                topic=topic
            )
            yield ReportEvent(type="section_completed", data=section_content)
        
        # 3. 整合输出
        final_report = await self.generator.compose_report(context)
        yield ReportEvent(type="report_completed", data=final_report)
```

---

## 四、场景2：模板化统计报告

### 4.1 方案B：临时报告（结构化拆解）

适用于一次性或偶尔使用的报告模板。

#### 流程设计

```
用户上传历史报告 + 目标时间段
    │
    ▼
┌─────────────────────────────────────┐
│ 阶段1: 报告解析 (ReportParser)      │
│                                     │
│ LLM分析报告，提取：                  │
│ - 报告结构（章节列表）               │
│ - 时间范围标识                      │
│ - 数据点清单（指标、城市、数值）     │
│ - 表格结构定义                      │
│ - 排名逻辑规则                      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 阶段2: 数据查询 (DataFetcher)       │
│                                     │
│ 根据解析结果，批量调用数据工具：     │
│ - get_air_quality(cities, new_range)│
│ - get_guangdong_regular_stations()  │
│ - 查询含同比变化的统计数据          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 阶段3: 数据整理 (DataOrganizer)     │
│                                     │
│ - 整理API返回的统计结果             │
│ - 格式化数据点（数值、百分比）       │
│ - 组装表格数据结构                  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 阶段4: 报告生成 (ReportRenderer)    │
│                                     │
│ LLM基于：                            │
│ - 原报告模板（结构+语言风格）        │
│ - 新数据集                          │
│ - 分析结论                          │
│ 生成更新后的报告                     │
└─────────────────────────────────────┘
    │
    ▼
Markdown报告 → Word导出
```

#### 核心组件

```python
# backend/app/services/template_report_engine.py

class TemplateReportEngine:
    """模板化报告引擎"""
    
    async def generate_from_template(
        self,
        template_content: str,
        target_time_range: TimeRange,
        options: Optional[ReportOptions] = None
    ) -> AsyncGenerator[ReportEvent, None]:
        """
        基于历史报告模板生成新报告
        
        Args:
            template_content: 历史报告内容（Markdown）
            target_time_range: 目标时间范围
            options: 生成选项
        """
        # 阶段1: 解析报告结构
        yield ReportEvent(type="phase_started", data={"phase": "parsing"})
        
        report_structure = await self.parser.parse(template_content)
        yield ReportEvent(type="structure_parsed", data=report_structure)
        
        # 阶段2: 数据查询
        yield ReportEvent(type="phase_started", data={"phase": "data_fetching"})
        
        data_requirements = report_structure.get_data_requirements()
        raw_data = await self.data_fetcher.fetch_all(
            requirements=data_requirements,
            time_range=target_time_range
        )
        yield ReportEvent(type="data_fetched", data={"record_count": len(raw_data)})
        
        # 阶段3: 数据整理
        yield ReportEvent(type="phase_started", data={"phase": "processing"})
        
        processed_data = await self.organizer.organize(
            raw_data=raw_data,
            data_points=report_structure.data_points
        )
        yield ReportEvent(type="data_organized", data=processed_data.summary())
        
        # 阶段4: 报告生成
        yield ReportEvent(type="phase_started", data={"phase": "rendering"})
        
        final_report = await self.renderer.render(
            template=template_content,
            structure=report_structure,
            data=processed_data,
            target_time_range=target_time_range
        )
        yield ReportEvent(type="report_completed", data=final_report)
```

#### 报告解析器

```python
# backend/app/services/report_parser.py

class ReportParser:
    """报告结构解析器"""
    
    async def parse(self, content: str) -> ReportStructure:
        """
        使用LLM解析报告结构
        
        Returns:
            ReportStructure: 包含章节、数据点、表格、排名规则
        """
        prompt = f"""分析以下报告，提取结构化信息：

{content}

请以JSON格式返回：
{{
    "time_range": {{
        "original": "1-6月",
        "start_month": 1,
        "end_month": 6,
        "year": 2025
    }},
    "sections": [
        {{
            "id": "overview",
            "title": "总体状况",
            "type": "text_with_data",
            "data_points": [
                {{"name": "AQI达标率", "value": 93.7, "unit": "%", "comparison": "同比下降2.7个百分点"}},
                {{"name": "PM2.5浓度", "value": 23, "unit": "微克/立方米", "comparison": "同比上升9.5%"}}
            ]
        }}
    ],
    "tables": [
        {{
            "id": "city_air_quality",
            "title": "全省城市环境空气质量状况",
            "columns": ["城市", "AQI达标率", "PM2.5浓度", ...],
            "row_type": "city"
        }}
    ],
    "rankings": [
        {{
            "id": "best_cities",
            "description": "空气质量较好的5市",
            "metric": "综合指数",
            "order": "asc",
            "top_n": 5
        }}
    ],
    "analysis_sections": [
        {{
            "id": "cause_analysis",
            "title": "原因分析",
            "type": "llm_generated",
            "input_data": ["weather", "emissions", "control_measures"]
        }}
    ]
}}
"""
        response = await llm_service.chat([{"role": "user", "content": prompt}])
        return ReportStructure.from_json(response)
```

### 4.2 方案C：固定报告（模板标注）

适用于周期性生成的固定格式报告。

#### ToolExecutor实现（通过ReAct Agent工具注册表）

```python
# backend/app/services/tool_executor.py

class ToolExecutor:
    """工具执行器 - 通过ReAct Agent工具注册表调用"""

    def __init__(self, react_agent):
        self.react_agent = react_agent  # 复用工具注册表

    async def execute_via_context(
        self,
        context: ExecutionContext,
        tool_call: ToolCall
    ) -> ToolResult:
        """
        通过ReAct Agent工具注册表执行工具

        Args:
            context: Context-Aware V2上下文
            tool_call: 工具调用信息
        """
        # 通过ReAct Agent的工具选择机制
        result = await self.react_agent.call_tool(
            tool_name=tool_call.name,
            parameters=tool_call.params
        )

        # 自动存储到Context-Aware V2（遵循架构）
        if result.success and result.data:
            data_id = context.save_data(
                data=result.data,
                schema=tool_call.schema or "report_data"
            )
            result.data_id = data_id

        return result
```

#### 流程设计

```
首次使用：
┌─────────────────────────────────────┐
│ 模板标注阶段                         │
│                                     │
│ 1. 用户上传历史报告                  │
│ 2. LLM自动识别并标注数据点           │
│ 3. 生成标注模板（含占位符）          │
│ 4. 用户校验/调整标注                 │
│ 5. 保存标注模板到模板库              │
└─────────────────────────────────────┘
    │
    ▼ 保存
┌─────────────────────────────────────┐
│ 模板库                               │
│ - 广东省月度空气质量通报.template    │
│ - 城市环境质量周报.template          │
│ - ...                               │
└─────────────────────────────────────┘

后续使用：
┌─────────────────────────────────────┐
│ 快速生成阶段                         │
│                                     │
│ 1. 选择已标注模板                    │
│ 2. 指定目标时间范围                  │
│ 3. 自动查询数据填充                  │
│ 4. LLM生成分析部分                   │
│ 5. 输出完整报告                      │
└─────────────────────────────────────┘
```

#### 标注模板格式

```markdown
# 全省城市空气和水环境质量通报
（{{time_range.display}}）

## 一、城市环境空气质量

**总体状况**：{{time_range.display}}，全省空气质量总体优良，同比{{aqi_yoy_trend}}；
全省优良天数比例（AQI达标率）为{{aqi_compliance_rate}}%，同比{{aqi_compliance_yoy}}；
细颗粒物（PM2.5）浓度为{{pm25_avg}}微克/立方米，同比{{pm25_yoy}}。
臭氧（O3）和PM2.5作为全省首要污染物的比例分别为{{o3_primary_ratio}}%和{{pm25_primary_ratio}}%。

**城市状况**：{{time_range.display}}，空气质量较好的5市是{{best_5_cities}}；
空气质量较差的5市是{{worst_5_cities}}。

**原因分析**：{{#llm_analysis}}
基于以下数据生成原因分析：
- 气象条件：{{weather_summary}}
- 污染排放：{{emission_summary}}
- 管控措施：{{control_summary}}
{{/llm_analysis}}

## 附表1 {{time_range.display}}全省城市环境空气质量状况

{{#table:city_air_quality}}
| 城市 | AQI达标率 | 同比 | PM2.5浓度 | 同比 | O3超标天数 | 综合指数 | 排名 |
|------|----------|------|----------|------|-----------|---------|------|
{{#each cities}}
| {{name}} | {{aqi_rate}}% | {{aqi_yoy}} | {{pm25}} | {{pm25_yoy}} | {{o3_exceed}} | {{composite}} | {{rank}} |
{{/each}}
{{/table}}
```

#### 模板管理服务

```python
# backend/app/services/template_manager.py

class TemplateManager:
    """报告模板管理服务"""
    
    async def create_template(
        self,
        name: str,
        source_report: str,
        user_id: str
    ) -> ReportTemplate:
        """
        从源报告创建标注模板
        
        Args:
            name: 模板名称
            source_report: 源报告内容
            user_id: 创建者
        """
        # LLM自动标注
        annotated = await self.annotator.annotate(source_report)
        
        template = ReportTemplate(
            id=str(uuid4()),
            name=name,
            content=annotated.template_content,
            placeholders=annotated.placeholders,
            data_sources=annotated.data_sources,
            created_by=user_id,
            version=1
        )
        
        await self.repository.save(template)
        return template
    
    async def generate_from_template(
        self,
        template_id: str,
        time_range: TimeRange
    ) -> str:
        """从模板快速生成报告"""
        template = await self.repository.get(template_id)
        
        # 获取数据
        data = await self.data_fetcher.fetch_for_template(
            template.data_sources,
            time_range
        )
        
        # 渲染模板
        report = await self.renderer.render(template, data)
        
        return report
```

---

## 五、数据查询策略

### 5.1 设计原则

**核心思路**：数据查询工具已支持同比/环比、达标率、排名等统计查询，报告生成模块不再重复计算，直接通过自然语言查询获取已计算结果。

### 5.2 数据获取器

```python
# backend/app/services/template_data_fetcher.py

class TemplateDataFetcher:
    """模板报告数据获取器 - 直接从API获取已计算的统计数据"""
    
    def __init__(self):
        self.query_tool = GetAirQualityTool()
    
    async def fetch_for_report(
        self,
        data_points: List[DataPoint],
        time_range: TimeRange
    ) -> Dict[str, Any]:
        """
        根据报告数据点需求，构造自然语言查询获取数据
        
        Args:
            data_points: 报告解析出的数据点清单
            time_range: 目标时间范围
        """
        results = {}
        
        # 按查询类型分组，减少API调用次数
        grouped_queries = self._group_data_points(data_points)
        
        for query_type, points in grouped_queries.items():
            question = self._build_query(query_type, points, time_range)
            result = await self.query_tool.execute(question=question)
            
            # 解析结果，映射到各数据点
            for point in points:
                results[point.id] = self._extract_value(result, point)
        
        return results
    
    def _build_query(
        self,
        query_type: str,
        points: List[DataPoint],
        time_range: TimeRange
    ) -> str:
        """构造自然语言查询"""
        
        display = time_range.display  # 如 "2025年1-7月"
        
        if query_type == "province_overview":
            # 省级概览：达标率、污染物均值、同比
            return f"查询广东省{display}空气质量概况，包括AQI达标率、PM2.5浓度、O3浓度及同比变化"
        
        elif query_type == "city_ranking":
            # 城市排名
            return f"查询广东省{display}空气质量排名，包括综合指数、PM2.5、O3排名前5和后5的城市"
        
        elif query_type == "district_ranking":
            # 区县排名
            return f"查询广东省{display}区县空气质量排名前20和后20"
        
        elif query_type == "city_detail_table":
            # 城市详细数据表
            return f"查询广东省21个地市{display}空气质量详细数据，包括AQI达标率、PM2.5、O3、综合指数及同比"
        
        elif query_type == "monthly_comparison":
            # 单月数据（如6月）
            month = points[0].month if points else time_range.end_month
            return f"查询广东省2025年{month}月空气质量数据及同比变化"
        
        else:
            # 通用查询
            return f"查询广东省{display}空气质量统计数据"
    
    def _group_data_points(self, points: List[DataPoint]) -> Dict[str, List[DataPoint]]:
        """将数据点按查询类型分组，优化API调用"""
        groups = defaultdict(list)
        
        for point in points:
            if point.scope == "province" and point.metric in ["aqi_rate", "pm25_avg", "o3_avg"]:
                groups["province_overview"].append(point)
            elif point.scope == "city" and point.type == "ranking":
                groups["city_ranking"].append(point)
            elif point.scope == "district" and point.type == "ranking":
                groups["district_ranking"].append(point)
            elif point.scope == "city" and point.type == "table":
                groups["city_detail_table"].append(point)
            else:
                groups["general"].append(point)
        
        return groups
```

### 5.3 查询示例

| 数据需求 | 自然语言查询 | API返回 |
|---------|-------------|---------|
| 省级AQI达标率 | "查询广东省2025年1-7月AQI达标率及同比" | `{rate: 93.2, yoy: -2.5}` |
| 空气质量Top5城市 | "查询广东省2025年1-7月空气质量最好的5个城市" | `["梅州", "汕头", "河源", ...]` |
| 城市详细表格 | "查询广东省21地市2025年1-7月空气质量详表" | `[{city, aqi_rate, pm25, ...}, ...]` |
| PM2.5同比变化 | "查询广东省2025年1-7月PM2.5浓度同比变化" | `{value: 24, yoy_pct: 8.5}` |

### 4.3 UDF v2.0输出格式规范

#### 报告数据统一格式

```python
# 所有报告生成输出必须符合UDF v2.0标准
{
    "status": "success",
    "success": true,
    "data": null,  # 报告不使用data字段
    "visuals": [  # 报告作为可视化的一种类型
        {
            "id": "report_001",
            "type": "markdown",  # 新增：报告markdown类型
            "schema": "chart_config",
            "payload": {
                "content": "# 报告内容\n...",  # Markdown完整内容
                "sections": [  # 章节结构
                    {
                        "id": "abstract",
                        "title": "摘要",
                        "content": "...",
                        "order": 1
                    },
                    {
                        "id": "methodology",
                        "title": "研究方法",
                        "content": "...",
                        "order": 2
                    }
                ],
                "word_export_url": "/exports/report_001.docx",  # Word导出链接
                "charts": [  # 嵌入的图表
                    {
                        "chart_id": "visual_001",
                        "section_id": "results",
                        "position": "inline"
                    }
                ]
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "ReportGenerationAgent",
                "source_data_ids": ["data_001", "data_002"],
                "scenario": "research_report",
                "layout_hint": "wide",
                "data_flow": ["report_generation", "markdown"]
            }
        }
    ],
    "metadata": {
        "schema_version": "v2.0",
        "field_mapping_applied": true,
        "field_mapping_info": {
            "standardization_applied": true,
            "field_mappings_count": 0,  # 报告无字段映射
            "unified_fields": []
        },
        "generator": "ReportGenerationAgent",
        "scenario": "research_report",
        "record_count": 1,
        "generator_version": "1.0.0"
    },
    "summary": "已完成研究报告生成，包含摘要、方法、结果、结论等章节"
}
```

#### 多图表场景支持

```python
{
    "status": "success",
    "success": true,
    "data": null,
    "visuals": [
        {
            "id": "report_main",
            "type": "markdown",
            "schema": "chart_config",
            "payload": {
                "content": "# 主报告内容\n...",
                "sections": [...]
            }
        },
        {
            "id": "chart_001",
            "type": "line",
            "schema": "chart_config",
            "payload": {
                "data": {...},
                "title": "PM2.5浓度趋势"
            },
            "meta": {
                "source_data_ids": ["pm25_data_001"],
                "scenario": "research_report"
            }
        },
        {
            "id": "chart_002",
            "type": "pie",
            "schema": "chart_config",
            "payload": {
                "data": [...],
                "title": "污染物占比"
            },
            "meta": {
                "source_data_ids": ["pollutant_data_001"],
                "scenario": "research_report"
            }
        }
    ],
    "metadata": {
        "schema_version": "v2.0",
        "generator": "ReportGenerationAgent",
        "scenario": "research_report"
    }
}
```

---

## 六、API设计

### 6.1 报告生成API

```python
# backend/app/routers/report_generation.py

router = APIRouter(prefix="/api/report", tags=["report-generation"])

@router.post("/generate")
async def generate_report(
    request: ReportGenerationRequest,
    background_tasks: BackgroundTasks
) -> StreamingResponse:
    """
    生成研究报告（流式返回）
    
    Request:
        {
            "topic": "2025年上半年广东省臭氧污染特征分析",
            "report_type": "research_report",
            "requirements": "重点分析珠三角地区",
            "knowledge_base_ids": ["kb_001", "kb_002"]
        }
    
    Response: SSE流
        event: plan_created
        data: {"sections": [...]}
        
        event: section_completed
        data: {"section_id": "background", "content": "..."}
        
        event: report_completed
        data: {"markdown": "...", "word_url": "..."}
    """
    agent = ReportGenerationAgent()
    
    async def event_generator():
        async for event in agent.generate(
            topic=request.topic,
            report_type=request.report_type,
            requirements=request.requirements,
            knowledge_base_ids=request.knowledge_base_ids
        ):
            yield f"event: {event.type}\ndata: {event.data_json()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.post("/generate-from-template")
async def generate_from_template(
    request: TemplateReportRequest
) -> StreamingResponse:
    """
    基于模板生成报告（流式返回）
    
    Request:
        {
            "template_content": "历史报告Markdown内容...",
            "target_time_range": {
                "start": "2025-01-01",
                "end": "2025-07-31"
            },
            "options": {
                "include_analysis": true,
                "include_charts": false
            }
        }
    """
    engine = TemplateReportEngine()
    
    async def event_generator():
        async for event in engine.generate_from_template(
            template_content=request.template_content,
            target_time_range=TimeRange(**request.target_time_range),
            options=request.options
        ):
            yield f"event: {event.type}\ndata: {event.data_json()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.post("/templates")
async def create_template(
    request: CreateTemplateRequest,
    current_user: User = Depends(get_current_user)
) -> TemplateResponse:
    """创建报告模板（方案C）"""
    manager = TemplateManager()
    template = await manager.create_template(
        name=request.name,
        source_report=request.source_report,
        user_id=current_user.id
    )
    return TemplateResponse.from_model(template)


@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_user)
) -> List[TemplateResponse]:
    """获取模板列表"""
    manager = TemplateManager()
    templates = await manager.list_templates(user_id=current_user.id)
    return [TemplateResponse.from_model(t) for t in templates]


@router.post("/templates/{template_id}/generate")
async def generate_from_saved_template(
    template_id: str,
    request: QuickGenerateRequest
) -> StreamingResponse:
    """从已保存模板快速生成"""
    manager = TemplateManager()
    
    async def event_generator():
        report = await manager.generate_from_template(
            template_id=template_id,
            time_range=TimeRange(**request.time_range)
        )
        yield f"event: report_completed\ndata: {json.dumps({'markdown': report})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 6.2 请求/响应模型

```python
# backend/app/schemas/report_generation.py

class ReportGenerationRequest(BaseModel):
    topic: str = Field(..., description="研究主题")
    report_type: str = Field("research_report", description="报告类型")
    requirements: Optional[str] = Field(None, description="额外要求")
    knowledge_base_ids: Optional[List[str]] = Field(None, description="知识库ID列表")


class TemplateReportRequest(BaseModel):
    template_content: str = Field(..., description="历史报告内容")
    target_time_range: Dict[str, str] = Field(..., description="目标时间范围")
    options: Optional[Dict[str, Any]] = Field(None, description="生成选项")


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., description="模板名称")
    source_report: str = Field(..., description="源报告内容")
    description: Optional[str] = Field(None, description="模板描述")


class QuickGenerateRequest(BaseModel):
    time_range: Dict[str, str] = Field(..., description="目标时间范围")
    options: Optional[Dict[str, Any]] = Field(None, description="生成选项")
```

---

## 七、前端设计

### 7.1 页面结构

```
报告生成页面
├── 场景选择器
│   ├── 研究报告生成（场景1）
│   └── 模板化报告生成（场景2）
│
├── 研究报告生成面板
│   ├── 主题输入框
│   ├── 报告类型选择
│   ├── 知识库选择（多选）
│   ├── 额外要求输入
│   └── 生成按钮
│
├── 模板报告生成面板
│   ├── 模板上传/选择
│   │   ├── 上传历史报告（临时）
│   │   └── 选择已保存模板（固定）
│   ├── 时间范围选择
│   └── 生成按钮
│
├── 生成进度面板
│   ├── 阶段进度条
│   ├── 当前操作提示
│   └── 工具调用日志（可折叠）
│
└── 报告预览/编辑面板
    ├── Markdown预览
    ├── 章节导航
    ├── 编辑模式切换
    └── 导出按钮（Word/PDF/HTML）
```

### 7.2 关键组件

```vue
<!-- frontend/src/components/report/ReportGenerationPanel.vue -->

<template>
  <div class="report-generation-panel">
    <!-- 场景选择 -->
    <div class="scenario-tabs">
      <button 
        :class="{ active: scenario === 'research' }"
        @click="scenario = 'research'"
      >
        研究报告生成
      </button>
      <button 
        :class="{ active: scenario === 'template' }"
        @click="scenario = 'template'"
      >
        模板化报告
      </button>
    </div>

    <!-- 研究报告表单 -->
    <div v-if="scenario === 'research'" class="research-form">
      <div class="form-group">
        <label>研究主题</label>
        <input v-model="researchForm.topic" placeholder="例：2025年上半年广东省臭氧污染特征分析" />
      </div>
      
      <div class="form-group">
        <label>报告类型</label>
        <select v-model="researchForm.reportType">
          <option value="research_report">研究报告</option>
          <option value="analysis_report">分析报告</option>
        </select>
      </div>
      
      <div class="form-group">
        <label>参考知识库</label>
        <KnowledgeBaseSelector v-model="researchForm.knowledgeBaseIds" />
      </div>
      
      <div class="form-group">
        <label>额外要求（可选）</label>
        <textarea v-model="researchForm.requirements" placeholder="例：重点分析珠三角地区" />
      </div>
      
      <button class="generate-btn" @click="generateResearchReport" :disabled="generating">
        {{ generating ? '生成中...' : '开始生成' }}
      </button>
    </div>

    <!-- 模板报告表单 -->
    <div v-if="scenario === 'template'" class="template-form">
      <div class="template-source">
        <div class="source-tabs">
          <button :class="{ active: templateSource === 'upload' }" @click="templateSource = 'upload'">
            上传历史报告
          </button>
          <button :class="{ active: templateSource === 'saved' }" @click="templateSource = 'saved'">
            选择已保存模板
          </button>
        </div>
        
        <div v-if="templateSource === 'upload'" class="upload-area">
          <input type="file" @change="handleFileUpload" accept=".md,.txt,.docx" />
          <div v-if="templateForm.content" class="preview">
            已加载: {{ templateForm.fileName }}
          </div>
        </div>
        
        <div v-if="templateSource === 'saved'" class="template-list">
          <TemplateSelector v-model="templateForm.templateId" />
        </div>
      </div>
      
      <div class="form-group">
        <label>目标时间范围</label>
        <DateRangePicker v-model="templateForm.timeRange" />
      </div>
      
      <button class="generate-btn" @click="generateTemplateReport" :disabled="generating">
        {{ generating ? '生成中...' : '开始生成' }}
      </button>
    </div>

    <!-- 生成进度 -->
    <GenerationProgress 
      v-if="generating" 
      :events="progressEvents"
      :current-phase="currentPhase"
    />

    <!-- 报告预览 -->
    <ReportPreview 
      v-if="reportContent"
      :content="reportContent"
      @export="handleExport"
    />
  </div>
</template>
```

---

## 八、实施计划

### 8.1 阶段划分

| 阶段 | 内容 | 工期 | 优先级 |
|------|------|------|--------|
| **P0** | 架构对齐（Context-Aware V2 + UDF v2.0） | 1天 | 高 |
| | - 集成ExecutionContext和DataContextManager | | |
| | - 统一UDF v2.0输出格式 | | |
| | - ToolExecutor通过ReAct Agent工具注册表 | | |
| **P1** | 核心功能实现（ReportGenerationAgent） | 5天 | 高 |
| | - ReportGenerationAgent（ReAct架构） | | |
| | - 场景1：研究报告生成 | | |
| | - 专家路由器集成 | | |
| | - 章节生成器 | | |
| **P2** | 场景2模板报告实现 | 3天 | 高 |
| | - 场景2-B：临时报告（结构化拆解） | | |
| | - 场景2-C：固定报告（模板标注） | | |
| | - 模板管理和快速生成 | | |
| **P3** | API路由和前端页面 | 2天 | 中 |
| | - API路由和请求模型 | | |
| | - 前端报告生成页面 | | |
| | - 集成现有多专家展示 | | |
| **P4** | 导出和优化 | 2天 | 中 |
| | - Word导出增强 | | |
| | - 图表嵌入 | | |
| | - 性能优化 | | |

### 8.2 文件结构

```
backend/app/
├── agent/
│   └── report_generation_agent.py    # 研究报告Agent (新增)
├── services/
│   ├── template_report_engine.py     # 模板报告引擎 (新增)
│   ├── report_parser.py              # 报告解析器 (新增)
│   ├── template_data_fetcher.py      # 数据获取器 (新增，复用现有工具)
│   ├── template_manager.py           # 模板管理 (新增)
│   └── report_exporter.py            # 报告导出 (已有，增强)
├── routers/
│   └── report_generation.py          # API路由 (新增)
└── schemas/
    └── report_generation.py          # 请求响应模型 (新增)

frontend/src/
├── views/
│   └── ReportGeneration.vue          # 报告生成页面 (新增)
├── components/
│   └── report/
│       ├── ReportGenerationPanel.vue # 生成面板 (新增)
│       ├── GenerationProgress.vue    # 进度展示 (新增)
│       ├── ReportPreview.vue         # 报告预览 (新增)
│       ├── TemplateSelector.vue      # 模板选择 (新增)
│       └── KnowledgeBaseSelector.vue # 知识库选择 (新增)
└── services/
    └── reportApi.js                  # API服务 (新增)
```

---

## 九、关键技术决策

### 9.1 LLM调用策略

| 场景 | 策略 | 原因 |
|------|------|------|
| 报告规划 | 单次调用 | 规划信息量小，一次完成 |
| 章节生成 | 逐章节调用 | 控制上下文长度，支持单章重试 |
| 报告解析 | 单次调用 | 需要完整理解报告结构 |
| 原因分析 | 单次调用 | 需要综合多维度数据 |

### 9.2 数据缓存

- 同一会话内的数据查询结果缓存
- 历史同期数据预加载
- 排名查询结果缓存

### 9.3 错误处理

- 工具调用失败：自动重试1次，失败后重新规划
- LLM生成失败：降级使用模板化输出
- 数据缺失：标注缺失字段，继续生成其他部分

---

## 十、验收标准

### 10.1 功能验收

- [ ] 研究报告：输入主题，生成包含背景、方法、结果、结论的完整报告
- [ ] 模板报告（临时）：上传历史报告，生成新时间段报告
- [ ] 模板报告（固定）：保存模板后，一键生成新报告
- [ ] 知识库引用：报告中正确引用知识库内容
- [ ] 数据准确：统计数据与源数据一致
- [ ] 导出功能：Word文档格式正确

### 10.2 性能指标

- 研究报告生成：< 2分钟（5章节）
- 模板报告生成：< 1分钟
- 首字节响应：< 3秒（流式）
