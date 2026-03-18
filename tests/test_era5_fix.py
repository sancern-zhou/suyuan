"""
Test script for era5_historical fix validation

This script verifies that the data_type parameter for get_weather_data
is correctly set to "era5" instead of the invalid "era5_historical".

Run: python -m pytest tests/test_era5_fix.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.agent.core.expert_plan_generator import ExpertPlanGenerator


class TestEra5Fix:
    """Test cases for era5_historical to era5 fix"""

    def test_structured_params_sync_era5_data_type(self):
        """Test that _generate_structured_params_sync sets data_type to 'era5'"""
        generator = ExpertPlanGenerator()
        context = {
            "location": "揭阳市",
            "lat": 23.5499,
            "lon": 116.3728,
            "start_time": "2024-12-24 00:00:00",
            "end_time": "2024-12-24 23:59:59",
            "expert_type": "weather"
        }

        params = generator._generate_structured_params_sync(
            tool_name="get_weather_data",
            context=context,
            upstream_data_ids=[]
        )

        # Verify data_type is 'era5' not 'era5_historical'
        assert "data_type" in params, "data_type should be in params"
        assert params["data_type"] == "era5", f"data_type should be 'era5', got '{params['data_type']}'"
        print(f"[PASS] data_type is correctly set to '{params['data_type']}'")

    @pytest.mark.asyncio
    async def test_async_structured_params_era5_data_type(self):
        """Test that _generate_structured_params (async) sets data_type to 'era5'"""
        generator = ExpertPlanGenerator()
        context = {
            "location": "揭阳市",
            "lat": 23.5499,
            "lon": 116.3728,
            "start_time": "2024-12-24 00:00:00",
            "end_time": "2024-12-24 23:59:59",
            "expert_type": "weather"
        }

        tool_spec = {
            "param_type": "structured",
            "required_params": ["data_type", "lat", "lon", "start_time", "end_time"]
        }

        params = await generator._generate_structured_params(
            tool_name="get_weather_data",
            tool_spec=tool_spec,
            context=context,
            upstream_data_ids=[]
        )

        # Verify data_type is 'era5' not 'era5_historical'
        assert "data_type" in params, "data_type should be in params"
        assert params["data_type"] == "era5", f"data_type should be 'era5', got '{params['data_type']}'"
        print(f"[PASS] async data_type is correctly set to '{params['data_type']}'")

    def test_get_weather_data_tool_spec(self):
        """Test that tool spec example is valid (era5 or observed)"""
        generator = ExpertPlanGenerator()
        tool_spec = generator.TOOL_SPECS.get("get_weather_data", {})

        # Verify the tool spec exists
        assert tool_spec is not None, "get_weather_data tool spec should exist"

        # Verify data_type enum only contains valid values
        # Tool spec uses 'parameters' directly for required_params
        required_params = tool_spec.get("required_params", [])
        assert "data_type" in required_params, "'data_type' should be a required param"

        # The tool schema is defined in LLMTool, check the enum in the tool definition
        # For this test, we verify the generated params contain valid data_type
        context = {
            "location": "test",
            "lat": 23.0,
            "lon": 113.0,
            "start_time": "2024-12-24 00:00:00",
            "end_time": "2024-12-24 23:59:59",
            "expert_type": "weather"
        }
        params = generator._generate_structured_params_sync(
            tool_name="get_weather_data",
            context=context,
            upstream_data_ids=[]
        )

        # Verify data_type is valid
        valid_types = ["era5", "observed"]
        assert params["data_type"] in valid_types, \
            f"data_type should be one of {valid_types}, got '{params['data_type']}'"
        assert params["data_type"] == "era5", \
            f"data_type should be 'era5', got '{params['data_type']}'"

        print(f"[PASS] Tool spec validation: data_type='{params['data_type']}'")

    def test_full_weather_plan_generation(self):
        """Test generating weather expert plan with valid data_type"""
        from app.agent.core.structured_query_parser import StructuredQuery

        generator = ExpertPlanGenerator()

        # Create a mock query for tracing analysis
        query = StructuredQuery(
            location="揭阳市",
            lat=23.5499,
            lon=116.3728,
            start_time="2024-12-24 00:00:00",
            end_time="2024-12-24 23:59:59",
            pollutants=["O3"],
            analysis_type="tracing"
        )

        # Generate expert plans
        tasks = generator.generate(query)

        # Verify weather expert exists
        assert "weather" in tasks, "Weather expert should be in tasks"

        weather_task = tasks["weather"]

        # Find get_weather_data tool in plan
        weather_tool_plan = None
        for plan in weather_task.tool_plan:
            if plan.tool == "get_weather_data":
                weather_tool_plan = plan
                break

        assert weather_tool_plan is not None, "get_weather_data should be in weather tool plan"
        assert weather_tool_plan.params.get("data_type") == "era5", \
            f"data_type should be 'era5', got '{weather_tool_plan.params.get('data_type')}'"

        print(f"[PASS] Weather plan generated with data_type='{weather_tool_plan.params.get('data_type')}'")


class TestUpwindAnalysisDependency:
    """Test that upwind analysis depends on weather data with correct params"""

    def test_upwind_analysis_params_structure(self):
        """Test that upwind analysis receives correct parameters structure"""
        generator = ExpertPlanGenerator()
        context = {
            "location": "揭阳市",
            "lat": 23.5499,
            "lon": 116.3728,
            "start_time": "2024-12-24 00:00:00",
            "end_time": "2024-12-24 23:59:59",
            "expert_type": "weather"
        }

        params = generator._generate_structured_params_sync(
            tool_name="analyze_upwind_enterprises",
            context=context,
            upstream_data_ids=["weather:v1:test123"]
        )

        # Verify upwind params structure
        assert "city_name" in params, "city_name should be in params"
        assert params["city_name"] == "揭阳市", f"city_name should be '揭阳市', got '{params['city_name']}'"
        assert "winds" in params, "winds should be in params"
        assert len(params["winds"]) > 0, "winds should not be empty"

        print(f"[PASS] Upwind analysis params: city_name='{params['city_name']}', winds count={len(params['winds'])}")


if __name__ == "__main__":
    # Run tests manually if script is executed directly
    print("=" * 60)
    print("Era5 Fix Validation Tests")
    print("=" * 60)

    test_instance = TestEra5Fix()

    try:
        print("\n[Test 1] Testing _generate_structured_params_sync...")
        test_instance.test_structured_params_sync_era5_data_type()
    except AssertionError as e:
        print(f"[FAIL] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

    try:
        print("\n[Test 2] Testing tool spec...")
        test_instance.test_get_weather_data_tool_spec()
    except AssertionError as e:
        print(f"[FAIL] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

    try:
        print("\n[Test 3] Testing full weather plan generation...")
        test_instance.test_full_weather_plan_generation()
    except AssertionError as e:
        print(f"[FAIL] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

    try:
        print("\n[Test 4] Testing upwind analysis params...")
        test_upwind = TestUpwindAnalysisDependency()
        test_upwind.test_upwind_analysis_params_structure()
    except AssertionError as e:
        print(f"[FAIL] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
