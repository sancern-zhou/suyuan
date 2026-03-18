"""
专家系统V3端到端测试

测试内容：
1. 结构化解析器
2. 专家选择器
3. 计划生成器
4. 专家执行器
5. 完整流水线
"""

import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


class TestStructuredQueryParser:
    """测试结构化查询解析器"""
    
    @pytest.mark.asyncio
    async def test_parse_simple_query(self):
        """测试简单查询解析"""
        from app.agent.core.structured_query_parser import StructuredQueryParser
        
        parser = StructuredQueryParser()
        
        # 使用正则降级（不调用LLM）
        result = parser._regex_extract("查询广州市昨天的空气质量")
        
        assert result["location"] == "广州"
        assert result["analysis_type"] == "query"
    
    def test_city_coordinates(self):
        """测试城市坐标映射"""
        from app.agent.core.structured_query_parser import StructuredQueryParser
        
        parser = StructuredQueryParser()
        
        lat, lon, _ = parser._resolve_location("肇庆市")
        assert lat == pytest.approx(23.0469, rel=0.01)
        assert lon == pytest.approx(112.4651, rel=0.01)
    
    def test_pollutant_normalization(self):
        """测试污染物标准化"""
        from app.agent.core.structured_query_parser import StructuredQueryParser
        
        parser = StructuredQueryParser()
        
        pollutants = parser._normalize_pollutants(["臭氧", "pm2.5", "NO2"])
        assert "O3" in pollutants
        assert "PM2.5" in pollutants
        assert "NO2" in pollutants


class TestExpertPlanGeneratorRouting:
    """测试专家选择逻辑被整合到计划生成器后是否正常"""
    
    def test_determine_required_experts_for_tracing(self):
        """溯源任务需要多个专家"""
        from app.agent.core.expert_plan_generator import ExpertPlanGenerator
        from app.agent.core.structured_query_parser import StructuredQuery
        
        generator = ExpertPlanGenerator()
        query = StructuredQuery(
            location="肇庆市",
            lat=23.0469,
            lon=112.4651,
            pollutants=["O3"],
            analysis_type="tracing",
            original_query="分析肇庆市臭氧污染溯源"
        )
        experts = generator.determine_required_experts(query)
        assert experts[:2] == ["weather", "component"]
        assert "report" in experts
    
    def test_determine_required_experts_for_simple_analysis(self):
        """普通分析至少包含组分专家"""
        from app.agent.core.expert_plan_generator import ExpertPlanGenerator
        from app.agent.core.structured_query_parser import StructuredQuery
        
        generator = ExpertPlanGenerator()
        query = StructuredQuery(
            location="广州",
            pollutants=["PM2.5"],
            analysis_type="analysis",
            original_query="评估广州PM2.5污染"
        )
        experts = generator.determine_required_experts(query)
        assert experts[0] == "component"
        assert "viz" in experts


class TestExpertPlanGenerator:
    """测试计划生成器"""
    
    def test_generate_weather_plan(self):
        """测试气象专家计划生成"""
        from app.agent.core.expert_plan_generator import ExpertPlanGenerator
        from app.agent.core.structured_query_parser import StructuredQuery
        
        generator = ExpertPlanGenerator()
        
        query = StructuredQuery(
            location="肇庆市",
            lat=23.0469,
            lon=112.4651,
            start_time="2025-11-07 00:00:00",
            end_time="2025-11-09 23:59:59",
            pollutants=["O3"],
            analysis_type="analysis",
            original_query="分析肇庆市气象条件"
        )
        
        tasks = generator.generate(query, ["weather"])
        
        assert "weather" in tasks
        weather_task = tasks["weather"]
        
        assert weather_task.expert_type == "weather"
        assert len(weather_task.tool_plan) > 0
        
        # 检查参数填充
        first_tool = weather_task.tool_plan[0]
        assert first_tool.params.get("lat") == 23.0469
        assert first_tool.params.get("lon") == 112.4651
    
    def test_generate_tracing_plan(self):
        """测试溯源分析计划生成"""
        from app.agent.core.expert_plan_generator import ExpertPlanGenerator
        from app.agent.core.structured_query_parser import StructuredQuery
        
        generator = ExpertPlanGenerator()
        
        query = StructuredQuery(
            location="肇庆市",
            lat=23.0469,
            lon=112.4651,
            start_time="2025-11-07 00:00:00",
            end_time="2025-11-09 23:59:59",
            pollutants=["O3"],
            analysis_type="tracing",
            original_query="分析肇庆市臭氧污染溯源"
        )
        
        tasks = generator.generate(query, ["weather", "component"])
        
        # 溯源分析应该有更多工具
        assert "weather" in tasks
        assert "component" in tasks


class TestExpertExecutor:
    """测试专家执行器"""
    
    def test_weather_executor_init(self):
        """测试气象执行器初始化"""
        from app.agent.experts.weather_executor import WeatherExecutor
        
        executor = WeatherExecutor()
        
        assert executor.expert_type == "weather"
        assert len(executor.tools) > 0
    
    def test_component_executor_init(self):
        """测试组分执行器初始化"""
        from app.agent.experts.component_executor import ComponentExecutor
        
        executor = ComponentExecutor()
        
        assert executor.expert_type == "component"
        assert len(executor.tools) > 0


class TestExpertRouterV3:
    """测试专家路由器V3"""
    
    def test_router_init(self):
        """测试路由器初始化"""
        from app.agent.experts.expert_router_v3 import ExpertRouterV3
        
        router = ExpertRouterV3()
        
        assert "weather" in router.executors
        assert "component" in router.executors
        assert "viz" in router.executors
        assert "report" in router.executors
    
    def test_get_executor_status(self):
        """测试获取执行器状态"""
        from app.agent.experts.expert_router_v3 import ExpertRouterV3
        
        router = ExpertRouterV3()
        status = router.get_executor_status()
        
        assert "weather" in status
        assert status["weather"]["available"] == True
    
    def test_parallel_grouping(self):
        """测试新的并行分组逻辑"""
        from app.agent.experts.expert_router_v3 import ExpertRouterV3
        
        router = ExpertRouterV3()
        groups = router._build_parallel_groups(["weather", "component", "viz", "report"])
        assert set(groups[0]) == {"weather", "component"}
        assert groups[1] == ["viz"]
        assert groups[2] == ["report"]


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_mock(self):
        """测试完整流水线（Mock LLM）"""
        from app.agent.experts.expert_router_v3 import ExpertRouterV3
        
        # Mock LLM服务
        with patch('app.agent.core.structured_query_parser.llm_service') as mock_llm:
            mock_llm.chat = AsyncMock(return_value=json.dumps({
                "location": "肇庆市",
                "time_start": "2025-11-07",
                "time_end": "2025-11-09",
                "pollutants": ["O3"],
                "analysis_type": "analysis"
            }))
            
            router = ExpertRouterV3()
            
            # 解析应该能工作
            parsed = await router.query_parser.parse("分析肇庆市臭氧")
            
            assert parsed.location == "肇庆市"
            assert "O3" in parsed.pollutants


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
