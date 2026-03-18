"""
Test PM2.5 tool execution flow
Trace why tools are not being executed
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.agent.core.expert_plan_generator import ExpertPlanGenerator
from app.agent.core.structured_query_parser import StructuredQuery
from app.agent.core.tool_dependencies import TOOL_DEPENDENCY_GRAPHS


def test_plan_generation():
    """Test if PM2.5 tools are in the generated plan"""

    print("=" * 60)
    print("Test 1: Plan Generation")
    print("=" * 60)

    # Create query
    query = StructuredQuery(
        location="深圳市",
        lat=22.5431,
        lon=114.0579,
        start_time="2026-02-01 00:00:00",
        end_time="2026-02-01 23:59:59",
        pollutants=["PM2.5"],
        analysis_type="tracing",
        time_granularity="hourly"
    )

    # Create plan generator
    generator = ExpertPlanGenerator()

    # Generate expert task
    task = generator._generate_expert_task(
        expert_type="component",
        query=query,
        upstream_results={}
    )

    print(f"\nGenerated task ID: {task.task_id}")
    print(f"Tool plan count: {len(task.tool_plan)}")
    print("\nTools in plan:")

    pm25_tools_found = []
    for i, plan in enumerate(task.tool_plan):
        print(f"  {i}. {plan.tool} - {plan.purpose}")
        if plan.tool in ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]:
            pm25_tools_found.append(plan.tool)
            print(f"     [PM2.5 TOOL FOUND]")
            print(f"     Params: {plan.params}")
            print(f"     Role: {plan.role}")

    print(f"\n" + "=" * 60)
    print(f"PM2.5 tools found: {len(pm25_tools_found)}/3")
    if len(pm25_tools_found) == 3:
        print("PASS: All PM2.5 tools are in the plan")
    else:
        print(f"FAIL: Missing tools: {set(['get_pm25_ionic', 'get_pm25_carbon', 'get_pm25_crustal']) - set(pm25_tools_found)}")
    print("=" * 60)

    return task


def test_tool_dependency_config():
    """Test if PM2.5 tools are in the dependency graph"""

    print("\n" + "=" * 60)
    print("Test 2: Tool Dependency Configuration")
    print("=" * 60)

    component_graph = TOOL_DEPENDENCY_GRAPHS.get("component", {})
    tools_config = component_graph.get("tools", {})

    pm25_tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    for tool_name in pm25_tools:
        if tool_name in tools_config:
            config = tools_config[tool_name]
            print(f"\n{tool_name}:")
            print(f"  depends_on: {config.get('depends_on', [])}")
            print(f"  produces: {config.get('produces', 'N/A')}")
            print(f"  timeout: {config.get('timeout', 'N/A')}")
            print(f"  max_retries: {config.get('max_retries', 'N/A')}")
            print(f"  [OK] Tool is in dependency graph")
        else:
            print(f"\n{tool_name}: [FAIL] NOT in dependency graph")

    print("\n" + "=" * 60)


def test_tool_loading():
    """Test if PM2.5 tools can be loaded"""

    print("\n" + "=" * 60)
    print("Test 3: Tool Loading")
    print("=" * 60)

    pm25_tools = {
        "get_pm25_ionic": "app.tools.query.get_pm25_ionic.tool.GetPM25IonicTool",
        "get_pm25_carbon": "app.tools.query.get_pm25_carbon.tool.GetPM25CarbonTool",
        "get_pm25_crustal": "app.tools.query.get_pm25_crustal.tool.GetPM25CrustalTool"
    }

    for tool_name, import_path in pm25_tools.items():
        try:
            module_path, class_name = import_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            tool_class = getattr(module, class_name)
            tool_instance = tool_class()
            print(f"\n{tool_name}:")
            print(f"  Class: {class_name}")
            print(f"  Name: {tool_instance.name}")
            print(f"  Category: {tool_instance.category}")
            print(f"  Requires context: {tool_instance.requires_context}")
            print(f"  [OK] Tool loaded successfully")
        except Exception as e:
            print(f"\n{tool_name}: [FAIL] {e}")

    print("\n" + "=" * 60)


def test_parameter_generation():
    """Test parameter generation for PM2.5 tools"""

    print("\n" + "=" * 60)
    print("Test 4: Parameter Generation")
    print("=" * 60)

    generator = ExpertPlanGenerator()

    context = {
        "location": "深圳市",
        "lat": 22.5431,
        "lon": 114.0579,
        "start_time": "2026-02-01 00:00:00",
        "end_time": "2026-02-01 23:59:59",
        "pollutants": ["PM2.5"],
        "analysis_type": "tracing",
        "time_granularity": "hourly",
        "expert_type": "component"
    }

    tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    for tool_name in tools:
        print(f"\n{tool_name}:")
        try:
            params = generator._generate_structured_params_sync(
                tool_name=tool_name,
                context=context,
                upstream_data_ids=[]
            )

            print(f"  Generated parameters:")
            for key, value in params.items():
                print(f"    {key}: {value}")

            # Check required parameters
            if "locations" in params:
                print(f"  [OK] locations parameter generated")
            else:
                print(f"  [WARN] locations parameter missing")

            if "start_time" in params and "end_time" in params:
                print(f"  [OK] time parameters generated")
            else:
                print(f"  [WARN] time parameters missing")

        except Exception as e:
            print(f"  [FAIL] Parameter generation failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("PM2.5 Tool Execution Flow Diagnostic")
    print("=" * 80)

    # Run all tests
    task = test_plan_generation()
    test_tool_dependency_config()
    test_tool_loading()
    test_parameter_generation()

    print("\n" + "=" * 80)
    print("Diagnostic Complete")
    print("=" * 80)

    print("\nSummary:")
    print("1. Check if PM2.5 tools are in the generated plan")
    print("2. Check if PM2.5 tools are in the dependency graph")
    print("3. Check if PM2.5 tools can be loaded")
    print("4. Check if parameters can be generated")
    print("\nIf all tests pass, the issue is in the execution layer.")
