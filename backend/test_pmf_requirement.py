"""Test PMF API Data - Check if PMF requirements are met"""
import asyncio
import httpx
import json

async def test_pmf_api():
    base_url = "http://180.184.91.74:9093/api/uqp/query"
    timeout = httpx.Timeout(120.0)

    print("=" * 80)
    print("PMF Data Requirement Test")
    print("=" * 80)

    # Test 1: Water-soluble ions
    print("\n[Test 1] Water-soluble ions")
    ion_query = {
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
        if resp.status_code == 200:
            data = resp.json()
            check_pmf_requirements("Ions", data)
        else:
            print(f"  ERROR: {resp.status_code}")

    # Test 2: Carbon components
    print("\n[Test 2] Carbon components")
    carbon_query = {
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
        if resp.status_code == 200:
            data = resp.json()
            check_pmf_requirements("Carbon", data)
        else:
            print(f"  ERROR: {resp.status_code}")

    print("\n" + "=" * 80)


def check_pmf_requirements(data_type, response):
    """Check if data meets PMF requirements"""
    print(f"  Data Type: {data_type}")
    print(f"  Response keys: {list(response.keys())}")

    # Check for error
    if 'error' in response:
        print(f"  [ERROR] API Error: {response.get('error')}")
        return

    # Check response structure
    if 'data' not in response:
        print(f"  [FAIL] No 'data' field in response")
        print(f"  Full response: {json.dumps(response, indent=2, ensure_ascii=False)[:500]}")
        return

    data_obj = response['data']
    if 'result' not in data_obj:
        print(f"  [FAIL] No 'result' field in data")
        return

    result = data_obj['result']

    # Get records
    if 'resultOne' in result:
        records = result['resultOne']
    elif 'resultData' in result:
        records = result['resultData']
    else:
        print(f"  [FAIL] No resultOne or resultData")
        return

    record_count = len(records)
    print(f"  Record Count: {record_count}")

    if record_count < 20:
        print(f"  [FAIL] Need >= 20 samples, got {record_count}")
        return
    else:
        print(f"  [PASS] Sample count >= 20")

    # Check fields
    if records:
        first = records[0]
        fields = list(first.keys())

        # Print all fields
        print(f"  All fields ({len(fields)}):")
        for f in fields:
            print(f"    - {repr(f)}")

        # PMF core components
        pmf_required = {"SO4", "NO3", "NH4", "OC", "EC"}
        pmf_found = set()

        for field in fields:
            # Normalize field name
            normalized = field.replace(" ", "").replace("_", "").replace("+", "")
            normalized = normalized.replace("\u207b", "").replace("\u00b2", "")  # Remove superscripts
            if normalized in pmf_required:
                pmf_found.add(normalized)

        print(f"\n  PMF Core Components:")
        print(f"    Required: {sorted(pmf_required)}")
        print(f"    Found: {sorted(pmf_found)}")
        print(f"    Missing: {sorted(pmf_required - pmf_found)}")
        print(f"    Coverage: {len(pmf_found)}/{len(pmf_required)}")

        if len(pmf_found) >= 3:
            print(f"  [PASS] PMF requirement met (>=3 components)")
        else:
            print(f"  [FAIL] PMF requirement NOT met (need >=3, got {len(pmf_found)})")


if __name__ == "__main__":
    asyncio.run(test_pmf_api())
