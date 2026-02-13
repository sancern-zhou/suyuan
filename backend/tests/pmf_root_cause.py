"""Detailed PMF Root Cause Analysis"""
import json
import sys

# Force UTF-8 output for Windows
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

def main():
    with open('tests/test_particulate_api_responses.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 80)
    print("PMF Root Cause Analysis")
    print("=" * 80)

    # Test 1: Water-soluble ions
    test1 = data['tests'][0]  # Water-soluble ions
    print(f"\n[Test 1] {test1['name']}")
    print(f"  Sample Count: {test1['list_1_count']}")
    print(f"  Fields: {test1['list_1_first_keys']}")

    if 'raw_response' in test1:
        raw = test1['raw_response']
        if 'data' in raw and 'result' in raw['data']:
            result = raw['data']['result']
            if 'resultOne' in result:
                first_record = result['resultOne'][0]
                print(f"\n  First Record Sample:")
                for key, value in first_record.items():
                    print(f"    {key}: {value}")

                # Count empty values
                empty_values = [k for k, v in first_record.items() if v == '—' or v == '' or v is None]
                valid_values = [k for k, v in first_record.items() if v != '—' and v != '' and v is not None]
                print(f"\n  Data Status:")
                print(f"    Valid fields: {len(valid_values)}")
                print(f"    Empty fields: {len(empty_values)}")
                print(f"    Valid field names: {valid_values}")

    # Test 2: Carbon components
    test2 = data['tests'][1]  # Carbon components
    print(f"\n[Test 2] {test2['name']}")
    print(f"  Sample Count: {test2['list_1_count']}")

    if 'list_1_first_keys' in test2:
        print(f"  Fields: {test2['list_1_first_keys']}")

    if 'raw_response' in test2:
        raw = test2['raw_response']
        if 'data' in raw and 'result' in raw['data']:
            result = raw['data']['result']
            if 'resultData' in result:
                result_data = result['resultData']
                if result_data:
                    first_record = result_data[0]
                    print(f"\n  First Record Sample:")
                    for key, value in first_record.items():
                        print(f"    {key}: {value}")

    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("=" * 80)

    # Analyze
    test1_samples = test1['list_1_count']
    test2_samples = test2['list_1_count']

    # Check fields
    test1_fields = test1['list_1_first_keys']
    test1_has_ions = any('SO4' in f or 'NO3' in f or 'NH4' in f for f in test1_fields)

    test2_fields = test2.get('list_1_first_keys', [])
    test2_has_carbon = any('OC' in f or 'EC' in f for f in test2_fields)

    print(f"1. Water-soluble ions:")
    print(f"   - Samples: {test1_samples} {'[PASS]' if test1_samples >= 20 else '[FAIL]'}")
    print(f"   - Has SO4/NO3/NH4 fields: {test1_has_ions} {'[PASS]' if test1_has_ions else '[FAIL]'}")

    print(f"\n2. Carbon components:")
    print(f"   - Samples: {test2_samples} {'[PASS]' if test2_samples >= 20 else '[FAIL]'}")
    print(f"   - Has OC/EC fields: {test2_has_carbon} {'[PASS]' if test2_has_carbon else '[FAIL]'}")

    print(f"\nROOT CAUSE:")
    if test1_samples >= 20 and test2_samples < 20:
        print("  -> Carbon components API returns only 1 sample (need >= 20)")
    elif test1_has_ions and not test2_has_carbon:
        print("  -> Carbon components API does not return OC/EC fields")
    elif test2_samples >= 20 and not test2_has_carbon:
        print("  -> Both APIs return samples but fields are missing")
    else:
        print("  -> Need to check actual API responses (data may be empty '—')")

if __name__ == "__main__":
    main()
