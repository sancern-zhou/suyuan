"""Test Particulate Matter API Data"""
import asyncio
import httpx

async def test_api():
    base_url = "http://180.184.91.74:9093/api/uqp/query"
    timeout = httpx.Timeout(120.0)

    # Test 1: Water-soluble ions
    print("\n=== Test 1: Water-soluble ions ===")
    ion_query = {
        "question": "Query PM2.5 water-soluble ions for Dongguan on 2026-01-27",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2026-01-27 00:00:00",
        "TimeEnd": "2026-01-27 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4", "Cl", "Ca", "Mg", "K", "Na"],
        "Station": "东莞",
        "Code": "1037b"
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(base_url, json=ion_query)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Response keys: {list(data.keys())}")
            if 'error' in data:
                print(f"API Error: {data.get('error')}")
                print(f"Full response: {data}")
            else:
                print_response("Water-soluble ions", data)
        else:
            print(f"ERROR: {resp.status_code}")
            print(f"Response: {resp.text}")

    # Test 2: Carbon components
    print("\n=== Test 2: Carbon components ===")
    carbon_query = {
        "question": "Query PM2.5 carbon components for Dongguan on 2026-01-27",
        "Detect": "ComponentPm25/GetComponentPm25Analysis",
        "TimeStart": "2026-01-27 00:00:00",
        "TimeEnd": "2026-01-27 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Station": "东莞",
        "Code": "1037b"
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(base_url, json=carbon_query)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Response keys: {list(data.keys())}")
            if 'error' in data:
                print(f"API Error: {data.get('error')}")
                print(f"Full response: {data}")
            else:
                print_response("Carbon components", data)
        else:
            print(f"ERROR: {resp.status_code}")
            print(f"Response: {resp.text}")

def print_response(data_type, response):
    """Analyze API response"""
    print(f"\nData Type: {data_type}")
    print(f"Keys: {list(response.keys())}")

    if "data" in response and "result" in response["data"]:
        result = response["data"]["result"]

        # Find records
        if "resultOne" in result:
            records = result["resultOne"]
        elif "resultData" in result:
            records = result["resultData"]
        else:
            print("No records found")
            return

        print(f"Records: {len(records)}")

        if records:
            first = records[0]
            print(f"First record keys: {list(first.keys())}")

            # Find component fields
            components = [k for k in first.keys() if k not in
                          ["TimePoint", "TimeType", "DataType", "Code", "StationName"]]

            print(f"Component fields ({len(components)}):")
            for field in sorted(components):
                sample_val = first.get(field)
                print(f"  {field}: {sample_val}")

            # PMF requirement check
            required = {"SO4", "NO3", "NH4", "OC", "EC"}
            available = set()

            for field in components:
                normalized = field.replace(" ", "").replace("_", "").replace("+", "")
                if normalized in required:
                    available.add(normalized)

            print(f"\nPMF Core Components:")
            print(f"  Required: {sorted(required)}")
            print(f"  Found: {sorted(available)}")
            print(f"  Missing: {sorted(required - available)}")
            print(f"  Coverage: {len(available)}/{len(required)} = {len(available)/len(required)*100:.0f}%")

            if len(available) >= 3:
                print("  [PASS] Meets PMF minimum requirement (>=3 components)")
            else:
                print("  [FAIL] Does NOT meet PMF requirement (need >=3 components)")

if __name__ == "__main__":
    asyncio.run(test_api())
