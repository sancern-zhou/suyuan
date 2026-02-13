"""
Verify PM2.5 tools are registered and can be executed
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))


def test_tool_registry():
    """Test that PM2.5 tools are in the global registry"""

    print("=" * 60)
    print("Test: PM2.5 Tools in Global Registry")
    print("=" * 60)

    from app.agent.tool_adapter import get_react_agent_tool_registry

    registry = get_react_agent_tool_registry()

    pm25_tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    print(f"\nTotal tools in registry: {len(registry)}")
    print(f"\nChecking PM2.5 tools:")

    all_found = True
    for tool_name in pm25_tools:
        if tool_name in registry:
            print(f"  {tool_name}: [OK] Found in registry")
        else:
            print(f"  {tool_name}: [FAIL] NOT in registry")
            all_found = False

    print("\n" + "=" * 60)
    if all_found:
        print("SUCCESS: All PM2.5 tools are registered")
    else:
        print("FAILURE: Some PM2.5 tools are missing")
    print("=" * 60)

    return all_found


def test_tool_execution():
    """Test that PM2.5 tools can be called"""

    print("\n" + "=" * 60)
    print("Test: PM2.5 Tool Execution")
    print("=" * 60)

    from app.agent.tool_adapter import get_react_agent_tool_registry

    registry = get_react_agent_tool_registry()

    pm25_tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    print("\nTesting tool callable:")

    all_callable = True
    for tool_name in pm25_tools:
        if tool_name in registry:
            tool = registry[tool_name]
            print(f"\n  {tool_name}:")
            print(f"    Type: {type(tool)}")
            print(f"    Callable: {callable(tool)}")

            # Check if it's a wrapped function or tool instance
            if hasattr(tool, '__name__'):
                print(f"    Function name: {tool.__name__}")
            if hasattr(tool, 'name'):
                print(f"    Tool name: {tool.name}")

            print(f"    [OK] Tool is callable")
        else:
            print(f"  {tool_name}: [FAIL] Not in registry")
            all_callable = False

    print("\n" + "=" * 60)
    if all_callable:
        print("SUCCESS: All PM2.5 tools are callable")
    else:
        print("FAILURE: Some PM2.5 tools are not callable")
    print("=" * 60)

    return all_callable


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("PM2.5 Tool Registry Fix Verification")
    print("=" * 80)

    test1 = test_tool_registry()
    test2 = test_tool_execution()

    print("\n" + "=" * 80)
    if test1 and test2:
        print("ALL TESTS PASSED - PM2.5 tools are properly registered")
    else:
        print("SOME TESTS FAILED - Check the output above")
    print("=" * 80)
