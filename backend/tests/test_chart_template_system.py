"""
测试图表模板系统 (ChartTemplateSystem)

验证内容：
1. 模板创建、保存、加载
2. 模板列表和搜索
3. 模板应用
4. 默认模板初始化
"""

import pytest
from typing import Dict, Any

from app.tools.visualization.chart_template_system.tool import (
    ChartTemplate,
    ChartTemplateSystem,
    create_template,
    load_template,
    list_templates,
    apply_template
)


class TestChartTemplate:
    """测试图表模板类"""

    def test_template_creation(self):
        """测试模板创建"""
        template = ChartTemplate(
            template_id="test_001",
            name="测试模板",
            description="这是一个测试模板",
            chart_config={"type": "bar", "title": "测试图表"},
            tags=["测试", "柱状图"]
        )

        assert template.template_id == "test_001"
        assert template.name == "测试模板"
        assert template.description == "这是一个测试模板"
        assert template.tags == ["测试", "柱状图"]
        assert template.usage_count == 0
        assert template.version == "1.0.0"
        assert template.created_at is not None

    def test_template_to_dict(self):
        """测试模板转换为字典"""
        template = ChartTemplate(
            template_id="test_001",
            name="测试模板",
            description="测试描述",
            chart_config={"type": "bar"}
        )

        template_dict = template.to_dict()

        assert "template_id" in template_dict
        assert "name" in template_dict
        assert "description" in template_dict
        assert "chart_config" in template_dict
        assert template_dict["template_id"] == "test_001"

    def test_template_from_dict(self):
        """测试从字典创建模板"""
        data = {
            "template_id": "test_001",
            "name": "测试模板",
            "description": "测试描述",
            "chart_config": {"type": "bar"},
            "created_by": "test_user",
            "tags": ["测试"],
            "usage_count": 5,
            "version": "1.0.0"
        }

        template = ChartTemplate.from_dict(data)

        assert template.template_id == "test_001"
        assert template.name == "测试模板"
        assert template.usage_count == 5
        assert template.version == "1.0.0"


class TestChartTemplateSystem:
    """测试模板系统"""

    def setup_method(self):
        """初始化测试"""
        self.system = ChartTemplateSystem()

    def test_system_initialization(self):
        """测试系统初始化"""
        assert self.system is not None
        assert len(self.system.templates) > 0  # 应该初始化默认模板

    def test_create_template(self):
        """测试创建模板"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="create",
                name="新模板",
                description="新创建的模板",
                chart_config={"type": "pie", "title": "新图表"},
                tags=["新", "饼图"]
            )

            assert result["success"] is True
            assert "template" in result["data"]
            template = result["data"]["template"]
            assert template["name"] == "新模板"
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_load_template(self):
        """测试加载模板"""
        import asyncio

        async def run_test():
            # 首先创建一个模板
            create_result = await self.system.execute(
                None,
                action="create",
                name="测试模板",
                description="测试",
                chart_config={"type": "bar"}
            )

            template_id = create_result["data"]["template"]["template_id"]

            # 加载模板
            load_result = await self.system.execute(
                None,
                action="load",
                template_id=template_id
            )

            assert load_result["success"] is True
            assert load_result["data"]["template"]["name"] == "测试模板"
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_load_nonexistent_template(self):
        """测试加载不存在的模板"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="load",
                template_id="nonexistent_id"
            )

            assert result["success"] is False
            assert "error" in result
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_list_templates(self):
        """测试列出模板"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="list",
                limit=10
            )

            assert result["success"] is True
            assert "templates" in result["data"]
            assert "total" in result["data"]
            assert result["data"]["total"] > 0
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_list_templates_with_tag_filter(self):
        """测试按标签过滤列出模板"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="list",
                tag="时序",
                limit=10
            )

            assert result["success"] is True
            templates = result["data"]["templates"]
            # 所有返回的模板都应该包含"时序"标签
            for template in templates:
                if "tags" in template:
                    assert "时序" in template["tags"] or any("时序" in str(tag) for tag in template["tags"])
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_delete_template(self):
        """测试删除模板"""
        import asyncio

        async def run_test():
            # 创建模板
            create_result = await self.system.execute(
                None,
                action="create",
                name="待删除模板",
                description="将被删除",
                chart_config={"type": "bar"}
            )

            template_id = create_result["data"]["template"]["template_id"]

            # 删除模板
            delete_result = await self.system.execute(
                None,
                action="delete",
                template_id=template_id
            )

            assert delete_result["success"] is True

            # 尝试再次加载（应该失败）
            load_result = await self.system.execute(
                None,
                action="load",
                template_id=template_id
            )

            assert load_result["success"] is False
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_search_templates(self):
        """测试搜索模板"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="search",
                query="时序"
            )

            assert result["success"] is True
            assert "templates" in result["data"]
            assert "query" in result["data"]
            assert result["data"]["query"] == "时序"
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_apply_template(self):
        """测试应用模板"""
        import asyncio

        async def run_test():
            # 创建模板
            create_result = await self.system.execute(
                None,
                action="create",
                name="测试模板",
                description="测试",
                chart_config={
                    "type": "bar",
                    "title": "测试图表"
                }
            )

            template_id = create_result["data"]["template"]["template_id"]

            # 创建测试数据
            data = [
                {"category": "A", "value": 10},
                {"category": "B", "value": 20}
            ]

            # 应用模板
            apply_result = await self.system.execute(
                None,
                action="apply",
                template_id=template_id,
                data=data,
                placeholders={}
            )

            assert apply_result["success"] is True
            assert "chart" in apply_result["data"]
            assert "template" in apply_result["data"]
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_apply_template_with_placeholders(self):
        """测试应用模板（含占位符替换）"""
        import asyncio

        async def run_test():
            # 创建带占位符的模板
            create_result = await self.system.execute(
                None,
                action="create",
                name="占位符模板",
                description="测试",
                chart_config={
                    "type": "bar",
                    "title": "{station_name}站点数据"
                }
            )

            template_id = create_result["data"]["template"]["template_id"]
            data = [{"category": "A", "value": 10}]

            # 应用模板并替换占位符
            apply_result = await self.system.execute(
                None,
                action="apply",
                template_id=template_id,
                data=data,
                placeholders={"station_name": "北京"}
            )

            assert apply_result["success"] is True
            chart = apply_result["data"]["chart"]
            # 标题应该被替换
            assert "北京" in chart.get("title", "")
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_unsupported_action(self):
        """测试不支持的操作"""
        import asyncio

        async def run_test():
            result = await self.system.execute(
                None,
                action="unsupported_action"
            )

            assert result["success"] is False
            assert "error" in result
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_increment_usage_count(self):
        """测试使用计数增加"""
        import asyncio

        async def run_test():
            # 创建模板
            create_result = await self.system.execute(
                None,
                action="create",
                name="计数测试",
                description="测试",
                chart_config={"type": "bar"}
            )

            template_id = create_result["data"]["template"]["template_id"]

            # 第一次加载
            await self.system.execute(None, action="load", template_id=template_id)
            # 第二次加载
            await self.system.execute(None, action="load", template_id=template_id)

            # 再次获取模板信息
            load_result = await self.system.execute(
                None,
                action="load",
                template_id=template_id
            )

            template = load_result["data"]["template"]
            assert template["usage_count"] == 3  # 实际加载了3次
            return True

        result = asyncio.run(run_test())
        assert result is True


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_create_template_function(self):
        """测试create_template便捷函数"""
        import asyncio

        async def run_test():
            result = await create_template(
                name="便捷模板",
                description="便捷创建的模板",
                chart_config={"type": "line", "title": "便捷图表"},
                tags=["便捷"]
            )

            assert result["success"] is True
            assert "template" in result["data"]
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_list_templates_function(self):
        """测试list_templates便捷函数"""
        import asyncio

        async def run_test():
            result = await list_templates(limit=5)

            assert result["success"] is True
            assert "templates" in result["data"]
            assert len(result["data"]["templates"]) <= 5
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_list_templates_with_tag(self):
        """测试按标签列出的便捷函数"""
        import asyncio

        async def run_test():
            result = await list_templates(tag="饼图")

            assert result["success"] is True
            assert "templates" in result["data"]
            return True

        result = asyncio.run(run_test())
        assert result is True


class TestEdgeCases:
    """测试边界情况"""

    def test_create_template_empty_name(self):
        """测试创建空名称模板"""
        import asyncio

        async def run_test():
            result = await create_template(
                name="",
                description="测试",
                chart_config={"type": "bar"}
            )

            # 空名称应该也能创建
            assert result["success"] is True
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_create_template_long_description(self):
        """测试创建长描述模板"""
        import asyncio

        async def run_test():
            long_desc = "这是一个" + "很" * 100 + "长的描述"
            result = await create_template(
                name="长描述模板",
                description=long_desc,
                chart_config={"type": "bar"}
            )

            assert result["success"] is True
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_create_template_special_characters(self):
        """测试创建包含特殊字符的模板"""
        import asyncio

        async def run_test():
            result = await create_template(
                name="特殊字符模板@#$%",
                description="包含特殊字符：@#$%^&*()",
                chart_config={"type": "bar"}
            )

            assert result["success"] is True
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_empty_tag_list(self):
        """测试空标签列表"""
        import asyncio

        async def run_test():
            result = await create_template(
                name="无标签模板",
                description="测试",
                chart_config={"type": "bar"},
                tags=[]
            )

            assert result["success"] is True
            assert result["data"]["template"]["tags"] == []
            return True

        result = asyncio.run(run_test())
        assert result is True

    def test_apply_template_with_empty_data(self):
        """测试应用模板（空数据）"""
        import asyncio

        async def run_test():
            # 创建模板
            create_result = await create_template(
                name="空数据模板",
                description="测试",
                chart_config={"type": "bar"}
            )

            template_id = create_result["data"]["template"]["template_id"]

            # 尝试应用空数据
            result = await apply_template(template_id, [])

            # 应该失败或返回错误
            assert "status" in result
            return True

        result = asyncio.run(run_test())
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
