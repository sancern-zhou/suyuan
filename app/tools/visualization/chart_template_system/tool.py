"""
图表模板系统 - 用户自定义模板保存与管理

核心功能：
1. 保存和加载自定义图表模板
2. 模板版本管理
3. 模板共享和复用
4. 快速基于模板生成图表

参考：docs/可视化增强方案.md 阶段3
"""

from typing import Dict, Any, Optional, List
import json
import uuid
from datetime import datetime

from abc import ABC, abstractmethod

logger = __import__('structlog').get_logger()


class ChartTemplate:
    """图表模板类"""

    def __init__(
        self,
        template_id: str,
        name: str,
        description: str,
        chart_config: Dict[str, Any],
        created_by: str = "system",
        tags: Optional[List[str]] = None
    ):
        self.template_id = template_id
        self.name = name
        self.description = description
        self.chart_config = chart_config
        self.created_by = created_by
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.tags = tags or []
        self.usage_count = 0
        self.version = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "chart_config": self.chart_config,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "usage_count": self.usage_count,
            "version": self.version
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChartTemplate':
        """从字典创建模板"""
        template = cls(
            template_id=data["template_id"],
            name=data["name"],
            description=data["description"],
            chart_config=data["chart_config"],
            created_by=data.get("created_by", "system")
        )
        template.created_at = data.get("created_at", template.created_at)
        template.updated_at = data.get("updated_at", template.updated_at)
        template.tags = data.get("tags", [])
        template.usage_count = data.get("usage_count", 0)
        template.version = data.get("version", "1.0.0")
        return template


class ChartTemplateSystem:
    """
    图表模板系统 - 管理自定义图表模板

    支持：
    1. 创建、保存、加载模板
    2. 模板版本管理
    3. 模板搜索和过滤
    4. 模板应用和实例化
    """

    def __init__(self):
        # 内存中的模板存储（生产环境应使用数据库）
        self.templates: Dict[str, ChartTemplate] = {}
        self._initialize_default_templates()

    def _initialize_default_templates(self):
        """初始化默认模板"""
        # 空气质量时序模板
        air_quality_timeseries = ChartTemplate(
            template_id="tpl_air_quality_timeseries",
            name="空气质量时序图",
            description="展示多个污染物随时间变化的时序图",
            chart_config={
                "type": "timeseries",
                "title": "{station_name}污染物浓度时序变化",
                "x_field": "timePoint",
                "y_fields": ["PM2.5", "O3", "PM10"],
                "colors": ["#ff6b6b", "#4ecdc4", "#45b7d1"],
                "grid": True,
                "legend": True
            },
            tags=["空气质量", "时序", "污染物"]
        )
        self.templates[air_quality_timeseries.template_id] = air_quality_timeseries

        # VOCs占比模板
        vocs_pie = ChartTemplate(
            template_id="tpl_vocs_pie",
            name="VOCs物种占比",
            description="展示VOCs各物种的浓度占比分布",
            chart_config={
                "type": "pie",
                "title": "{station_name}VOCs物种占比",
                "category_field": "species_name",
                "value_field": "concentration",
                "top_n": 10,
                "sort": "descending",
                "colors": "category10"
            },
            tags=["VOCs", "占比", "饼图"]
        )
        self.templates[vocs_pie.template_id] = vocs_pie

        # 多站点对比模板
        multi_station_bar = ChartTemplate(
            template_id="tpl_multi_station_bar",
            name="多站点污染物对比",
            description="对比多个站点的污染物平均浓度",
            chart_config={
                "type": "bar",
                "title": "{pollutant}多站点浓度对比",
                "x_field": "station_name",
                "y_field": "PM2.5",
                "aggregation": "mean",
                "top_n": 15,
                "sort": "descending",
                "horizontal": False,
                "colors": "#4ecdc4"
            },
            tags=["对比", "多站点", "柱状图"]
        )
        self.templates[multi_station_bar.template_id] = multi_station_bar

        # 风向玫瑰图模板
        wind_rose = ChartTemplate(
            template_id="tpl_wind_rose",
            name="风向玫瑰图",
            description="展示风向和风速的分布",
            chart_config={
                "type": "wind_rose",
                "title": "{station_name}风向玫瑰图",
                "direction_field": "windDirection",
                "speed_field": "windSpeed",
                "sectors": 16,
                "colors": "wind_scale"
            },
            tags=["气象", "风向", "风速"]
        )
        self.templates[wind_rose.template_id] = wind_rose

        # 边界层廓线模板
        pbl_profile = ChartTemplate(
            template_id="tbl_pbl_profile",
            name="边界层廓线",
            description="展示边界层高度和气象要素的垂直分布",
            chart_config={
                "type": "profile",
                "title": "{station_name}边界层廓线",
                "x_fields": ["temperature", "windSpeed"],
                "y_field": "altitude",
                "show_pbl": True,
                "colors": ["#ff6b6b", "#4ecdc4"]
            },
            tags=["气象", "边界层", "廓线"]
        )
        self.templates[pbl_profile.template_id] = pbl_profile

        # PMF结果模板
        pmf_pie = ChartTemplate(
            template_id="tpl_pmf_pie",
            name="PMF源解析结果",
            description="展示PMF分析的污染源贡献率",
            chart_config={
                "type": "pie",
                "title": "{station_name}污染源贡献率",
                "category_field": "source_name",
                "value_field": "contribution_pct",
                "sort": "descending",
                "show_percentage": True,
                "colors": "source_palette"
            },
            tags=["PMF", "源解析", "饼图"]
        )
        self.templates[pmf_pie.template_id] = pmf_pie

        logger.info("default_templates_initialized", count=len(self.templates))

    async def execute(
        self,
        context: Any,
        action: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行模板系统操作

        Args:
            context: 执行上下文
            action: 操作类型（create, save, load, list, delete, apply）
            **kwargs: 操作参数

        Returns:
            操作结果
        """
        logger.info("chart_template_system_action", action=action)

        try:
            if action == "create":
                return await self._create_template(**kwargs)
            elif action == "save":
                return await self._save_template(**kwargs)
            elif action == "load":
                return await self._load_template(**kwargs)
            elif action == "list":
                return await self._list_templates(**kwargs)
            elif action == "delete":
                return await self._delete_template(**kwargs)
            elif action == "apply":
                return await self._apply_template(**kwargs)
            elif action == "search":
                return await self._search_templates(**kwargs)
            else:
                raise ValueError(f"不支持的操作类型: {action}")

        except Exception as e:
            logger.error("chart_template_system_error", action=action, error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e)
            }

    async def _create_template(
        self,
        name: str,
        description: str,
        chart_config: Dict[str, Any],
        created_by: str = "user",
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """创建新模板"""
        template_id = f"tpl_{str(uuid.uuid4())[:8]}"
        template = ChartTemplate(
            template_id=template_id,
            name=name,
            description=description,
            chart_config=chart_config,
            created_by=created_by,
            tags=tags
        )

        self.templates[template_id] = template

        return {
            "status": "success",
            "success": True,
            "data": {
                "template": template.to_dict()
            },
            "summary": f"成功创建模板：{name}"
        }

    async def _save_template(
        self,
        template: ChartTemplate
    ) -> Dict[str, Any]:
        """保存模板"""
        template_id = template.template_id
        if template_id in self.templates:
            # 更新现有模板
            self.templates[template_id] = template
            template.updated_at = datetime.now().isoformat()
            return {
                "status": "success",
                "success": True,
                "data": {
                    "template": template.to_dict()
                },
                "summary": f"更新模板：{template.name}"
            }
        else:
            # 保存新模板
            self.templates[template_id] = template
            return {
                "status": "success",
                "success": True,
                "data": {
                    "template": template.to_dict()
                },
                "summary": f"保存模板：{template.name}"
            }

    async def _load_template(
        self,
        template_id: str
    ) -> Dict[str, Any]:
        """加载模板"""
        template = self.templates.get(template_id)
        if not template:
            return {
                "status": "failed",
                "success": False,
                "error": f"模板不存在: {template_id}"
            }

        # 增加使用计数
        template.usage_count += 1

        return {
            "status": "success",
            "success": True,
            "data": {
                "template": template.to_dict()
            },
            "summary": f"加载模板：{template.name}"
        }

    async def _list_templates(
        self,
        tag: Optional[str] = None,
        created_by: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """列出模板"""
        templates = list(self.templates.values())

        # 过滤
        if tag:
            templates = [t for t in templates if tag in t.tags]

        if created_by:
            templates = [t for t in templates if t.created_by == created_by]

        # 按使用次数排序
        templates.sort(key=lambda t: t.usage_count, reverse=True)
        templates = templates[:limit]

        # 转换为字典
        templates_dict = [t.to_dict() for t in templates]

        return {
            "status": "success",
            "success": True,
            "data": {
                "templates": templates_dict,
                "total": len(templates_dict),
                "filters": {
                    "tag": tag,
                    "created_by": created_by
                }
            },
            "summary": f"找到{len(templates_dict)}个模板"
        }

    async def _delete_template(
        self,
        template_id: str
    ) -> Dict[str, Any]:
        """删除模板"""
        if template_id not in self.templates:
            return {
                "status": "failed",
                "success": False,
                "error": f"模板不存在: {template_id}"
            }

        template_name = self.templates[template_id].name
        del self.templates[template_id]

        return {
            "status": "success",
            "success": True,
            "summary": f"删除模板：{template_name}"
        }

    async def _apply_template(
        self,
        template_id: str,
        data: Any,
        **kwargs
    ) -> Dict[str, Any]:
        """应用模板生成图表"""
        template = self.templates.get(template_id)
        if not template:
            return {
                "status": "failed",
                "success": False,
                "error": f"模板不存在: {template_id}"
            }

        # 增加使用计数
        template.usage_count += 1

        # 生成图表配置
        chart_config = template.chart_config.copy()

        # 替换占位符
        placeholders = kwargs.get("placeholders", {})
        for key, value in placeholders.items():
            if isinstance(chart_config["title"], str):
                chart_config["title"] = chart_config["title"].replace(f"{{{key}}}", str(value))

        # 生成图表
        from app.utils.chart_data_converter import convert_chart_data
        from app.tools.visualization.data_summarizer import DataSummarizer

        # 先分析数据
        summarizer = DataSummarizer()
        data_summary = summarizer.summarize(data)

        # 调用转换器生成图表
        chart_type = chart_config.get("type", "bar")
        converted_chart = convert_chart_data(data, chart_type=chart_type)

        # 应用模板配置
        if "title" in chart_config:
            converted_chart["title"] = chart_config["title"]

        # 添加模板元数据
        converted_chart["meta"] = converted_chart.get("meta", {})
        converted_chart["meta"]["template_id"] = template_id
        converted_chart["meta"]["template_name"] = template.name

        return {
            "status": "success",
            "success": True,
            "data": {
                "chart": converted_chart,
                "template": template.to_dict(),
                "data_summary": data_summary
            },
            "summary": f"使用模板'{template.name}'生成图表"
        }

    async def _search_templates(
        self,
        query: str
    ) -> Dict[str, Any]:
        """搜索模板"""
        query_lower = query.lower()
        matched_templates = []

        for template in self.templates.values():
            # 搜索名称、描述、标签
            if (query_lower in template.name.lower() or
                query_lower in template.description.lower() or
                any(query_lower in tag.lower() for tag in template.tags)):
                matched_templates.append(template)

        matched_templates.sort(key=lambda t: t.usage_count, reverse=True)

        return {
            "status": "success",
            "success": True,
            "data": {
                "templates": [t.to_dict() for t in matched_templates],
                "query": query,
                "count": len(matched_templates)
            },
            "summary": f"搜索'{query}'找到{len(matched_templates)}个模板"
        }


# ============================================
# 便捷函数
# ============================================

async def create_template(
    name: str,
    description: str,
    chart_config: Dict[str, Any],
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """快速创建模板"""
    system = ChartTemplateSystem()
    return await system.execute(
        None,  # mock context
        action="create",
        name=name,
        description=description,
        chart_config=chart_config,
        tags=tags
    )


async def load_template(template_id: str) -> Dict[str, Any]:
    """快速加载模板"""
    system = ChartTemplateSystem()
    return await system.execute(None, action="load", template_id=template_id)


async def list_templates(
    tag: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """快速列出模板"""
    system = ChartTemplateSystem()
    return await system.execute(None, action="list", tag=tag, limit=limit)


async def apply_template(
    template_id: str,
    data: Any,
    placeholders: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """快速应用模板"""
    system = ChartTemplateSystem()
    return await system.execute(
        None,
        action="apply",
        template_id=template_id,
        data=data,
        placeholders=placeholders or {}
    )


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """示例：创建和使用模板"""
        # 创建自定义模板
        print("=== 创建自定义模板 ===")
        custom_config = {
            "type": "bar",
            "title": "自定义图表 - {pollutant}",
            "x_field": "station_name",
            "y_field": "pollutant",
            "colors": "#ff9999"
        }

        result = await create_template(
            name="自定义污染物对比图",
            description="自定义的污染物对比柱状图模板",
            chart_config=custom_config,
            tags=["自定义", "污染物", "对比"]
        )

        if result["success"]:
            template_id = result["data"]["template"]["template_id"]
            print(f"创建成功，模板ID: {template_id}")

            # 列出所有模板
            print("\n=== 列出所有模板 ===")
            list_result = await list_templates()
            print(f"模板总数: {list_result['data']['total']}")

            # 搜索模板
            print("\n=== 搜索模板 ===")
            search_result = await search_templates("时序")
            print(f"搜索结果数: {search_result['data']['count']}")

    async def search_templates(query: str) -> Dict[str, Any]:
        """搜索模板"""
        system = ChartTemplateSystem()
        return await system.execute(None, action="search", query=query)

    asyncio.run(example())
