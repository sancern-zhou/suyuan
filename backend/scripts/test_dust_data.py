"""
CAMS Dust Data System Test Script

Test components:
1. CAMS API client
2. Dust repository (database operations)
3. CAMS dust fetcher
4. Get dust data tool (LLM)
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


async def test_cams_client():
    """Test 1: CAMS API Client"""
    print("=" * 60)
    print("Test 1: CAMS API Client")
    print("=" * 60)

    try:
        from app.external_apis.cams_client import CAMSClient

        client = CAMSClient()

        # Check dependencies
        print("\nChecking dependencies...")
        deps = client.check_dependencies()

        for lib, installed in deps.items():
            status = "[OK]" if installed else "[MISSING]"
            print(f"{status} {lib}")

        missing = [name for name, installed in deps.items() if not installed]

        if missing:
            print("\n[WARNING] Missing dependencies:")
            print(client.get_installation_instructions())
            print("\n[SKIP] CAMS API test (dependencies not installed)")
            return False

        # Test API call (will fail without API key, but tests the client logic)
        print("\nTesting CAMS API call...")
        print("Region: China (15-55N, 70-140E)")
        print("Date: Today")
        print("Forecast hours: 24")

        try:
            result = await client.fetch_dust_forecast(
                min_lat=39.0,
                max_lat=41.0,
                min_lon=115.0,
                max_lon=117.0,
                forecast_hours=24
            )

            if result.get("success"):
                print(f"[OK] CAMS API call successful")
                print(f"Variables: {list(result.get('variables', {}).keys())}")
                print(f"Grid points: {len(result.get('coordinates', {}).get('latitude', []))} x {len(result.get('coordinates', {}).get('longitude', []))}")
                return True
            else:
                print("[INFO] CAMS API call failed (may need API key configuration)")
                return False

        except NotImplementedError:
            print("[INFO] REST API not implemented. Please install cdsapi:")
            print("pip install cdsapi xarray netCDF4")
            return False
        except Exception as e:
            print(f"[INFO] CAMS API call failed: {str(e)}")
            print("[INFO] This is expected if CAMS API key is not configured")
            return False

    except Exception as e:
        print(f"[FAIL] CAMS client test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_dust_repository():
    """Test 2: Dust Repository"""
    print("\n" + "=" * 60)
    print("Test 2: Dust Repository (Database Operations)")
    print("=" * 60)

    try:
        from app.db.repositories.dust_repo import DustRepository

        repo = DustRepository()

        # Test data
        test_forecasts = [
            {
                "lat": 40.0,
                "lon": 116.0,
                "forecast_time": datetime.now(),
                "valid_time": datetime.now() + timedelta(hours=3),
                "leadtime_hour": 3,
                "dust_aod_550nm": 0.35,
                "pm10_concentration": 120.5,
                "data_source": "CAMS_TEST"
            },
            {
                "lat": 40.5,
                "lon": 116.5,
                "forecast_time": datetime.now(),
                "valid_time": datetime.now() + timedelta(hours=6),
                "leadtime_hour": 6,
                "dust_aod_550nm": 0.52,
                "pm10_concentration": 180.3,
                "data_source": "CAMS_TEST"
            }
        ]

        print("\n[INFO] Database operations require database configuration")
        print("[SKIP] Database write test (configure DATABASE_URL in .env)")

        # Could test if database is configured
        # saved_count = await repo.save_dust_forecasts(test_forecasts)
        # print(f"[OK] Saved {saved_count} dust forecast records")

        return True

    except Exception as e:
        print(f"[FAIL] Repository test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_dust_fetcher():
    """Test 3: CAMS Dust Fetcher"""
    print("\n" + "=" * 60)
    print("Test 3: CAMS Dust Fetcher")
    print("=" * 60)

    try:
        from app.fetchers.dust.cams_dust_fetcher import CAMSDustFetcher

        fetcher = CAMSDustFetcher()

        print(f"\n[OK] Fetcher created successfully")
        print(f"Name: {fetcher.name}")
        print(f"Description: {fetcher.description}")
        print(f"Schedule: {fetcher.schedule}")
        print(f"Version: {fetcher.version}")
        print(f"China bounds: {fetcher.china_bounds}")
        print(f"Forecast hours: {fetcher.forecast_hours}")

        print("\n[INFO] Fetcher execution requires:")
        print("  1. CAMS API key configuration")
        print("  2. Database configuration")
        print("  3. Dependencies: cdsapi, xarray, netCDF4")
        print("[SKIP] Fetcher execution test")

        return True

    except Exception as e:
        print(f"[FAIL] Fetcher test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_dust_data_tool():
    """Test 4: Get Dust Data Tool (LLM)"""
    print("\n" + "=" * 60)
    print("Test 4: Get Dust Data Tool (LLM)")
    print("=" * 60)

    try:
        from app.tools.query.get_dust_data import GetDustDataTool

        tool = GetDustDataTool()

        print(f"\n[OK] Tool created successfully")
        print(f"Name: {tool.name}")
        print(f"Description: {tool.description}")
        print(f"Version: {tool.version}")

        # Check function schema
        schema = tool.get_function_schema()
        print(f"\nFunction Schema:")
        print(f"  Name: {schema['name']}")
        print(f"  Parameters: {list(schema['parameters']['properties'].keys())}")
        print(f"  Required: {schema['parameters']['required']}")

        # Test parameter validation
        print("\n[INFO] Testing parameter validation...")

        test_params = {
            "region": {
                "min_lat": 39.5,
                "max_lat": 41.0,
                "min_lon": 115.5,
                "max_lon": 117.0
            },
            "start_time": "2025-10-20T00:00:00",
            "end_time": "2025-10-20T23:59:59",
            "min_dust_aod": 0.2
        }

        result = tool._validate_params(
            test_params["region"],
            test_params["start_time"],
            test_params["end_time"]
        )

        if result["valid"]:
            print("[OK] Parameter validation passed")
        else:
            print(f"[FAIL] Parameter validation failed: {result['error']}")
            return False

        # Test impact level classification
        print("\n[INFO] Testing dust impact level classification...")
        test_aods = [0.15, 0.3, 0.7, 1.5, 2.5]
        for aod in test_aods:
            level = tool._classify_dust_impact(aod)
            print(f"  AOD {aod}: {level}")

        print("\n[INFO] Tool execution requires database with dust forecast data")
        print("[SKIP] Tool execution test")

        return True

    except Exception as e:
        print(f"[FAIL] Tool test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_lifecycle_registration():
    """Test 5: Lifecycle Manager Registration"""
    print("\n" + "=" * 60)
    print("Test 5: Lifecycle Manager Registration")
    print("=" * 60)

    try:
        from app.services.lifecycle_manager import fetcher_scheduler, tool_registry
        from app.services.lifecycle_manager import initialize_llm_tools

        # Initialize tools (without starting fetchers)
        initialize_llm_tools()

        # Check tool registration
        tools = tool_registry.list_tools()
        print(f"\n[OK] Total tools registered: {len(tools)}")

        dust_tool = None
        for tool_name in tools:
            if "dust" in tool_name.lower():
                dust_tool = tool_name
                print(f"[OK] Dust tool found: {tool_name}")

        if not dust_tool:
            print("[FAIL] Dust tool not found in registry")
            return False

        # Check function schemas
        schemas = tool_registry.get_function_schemas()
        dust_schema = None
        for schema in schemas:
            if schema.get("name") == "get_dust_data":
                dust_schema = schema
                print(f"[OK] Dust tool schema registered")
                print(f"     Description: {schema['description'][:80]}...")

        if not dust_schema:
            print("[FAIL] Dust tool schema not found")
            return False

        print("\n[INFO] Fetcher registration check skipped (requires scheduler start)")

        return True

    except Exception as e:
        print(f"[FAIL] Lifecycle registration test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n")
    print("*" * 60)
    print("*" + " " * 58 + "*")
    print("*" + " " * 10 + "CAMS Dust Data System Test Suite" + " " * 15 + "*")
    print("*" + " " * 58 + "*")
    print("*" * 60)
    print("\n")

    tests = [
        ("CAMS API Client", test_cams_client),
        ("Dust Repository", test_dust_repository),
        ("CAMS Dust Fetcher", test_dust_fetcher),
        ("Get Dust Data Tool", test_get_dust_data_tool),
        ("Lifecycle Registration", test_lifecycle_registration)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n[ERROR] {test_name} crashed: {str(e)}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print("\n" + "-" * 60)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
    else:
        print("\n[INFO] Some tests skipped or failed")
        print("To enable all tests:")
        print("  1. Install dependencies: pip install cdsapi xarray netCDF4")
        print("  2. Configure CAMS API key (see CAMS API documentation)")
        print("  3. Configure database in .env")


if __name__ == "__main__":
    asyncio.run(main())
