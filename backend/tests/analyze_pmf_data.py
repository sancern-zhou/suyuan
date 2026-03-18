"""Analyze PMF data from test_particulate_api_responses.json"""
import json

def analyze_pmf_requirement():
    with open('tests/test_particulate_api_responses.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 80)
    print("PMF Requirement Analysis from Cached API Responses")
    print("=" * 80)

    for test in data['tests']:
        print(f"\n[Test] {test['name']}")
        print(f"  Records: {test.get('list_1_count', 0)}")

        if test.get('list_1_first_keys'):
            fields = test['list_1_first_keys']
            print(f"  Fields ({len(fields)}):")

            # Show component fields (exclude metadata)
            component_fields = [f for f in fields if f not in
                              ['Code', 'StationName', 'TimePoint', 'PM2.5', 'PM2_5', 'AQI']]

            for field in component_fields:
                # Safe output: encode Unicode
                safe_name = field.encode('ascii', 'replace').decode('ascii')
                print(f"    - {safe_name}")

            # Check PMF requirements
            pmf_required = {"SO4", "NO3", "NH4", "OC", "EC"}
            pmf_found = set()

            for field in component_fields:
                # Normalize: remove superscripts and subscripts
                normalized = field.replace(" ", "").replace("_", "").replace("+", "")
                normalized = normalized.replace("\u207b", "")  # superscript -
                normalized = normalized.replace("\u00b2", "")  # superscript 2
                normalized = normalized.replace("\u2070", "")  # superscript 0
                normalized = normalized.replace("\u00b3", "")  # superscript 3
                normalized = normalized.replace("\u2082", "")  # subscript 2
                normalized = normalized.replace("\u2084", "")  # subscript 4
                normalized = normalized.replace("\u2081", "")  # subscript 1

                if normalized in pmf_required:
                    pmf_found.add(normalized)

            print(f"\n  PMF Core Components:")
            print(f"    Required: {sorted(pmf_required)}")
            print(f"    Found: {sorted(pmf_found)}")
            print(f"    Missing: {sorted(pmf_required - pmf_found)}")
            print(f"    Coverage: {len(pmf_found)}/{len(pmf_required)}")

            if test['list_1_count'] >= 20 and len(pmf_found) >= 3:
                print(f"  [PASS] Meets PMF requirements")
            else:
                reasons = []
                if test['list_1_count'] < 20:
                    reasons.append(f"samples < 20 ({test['list_1_count']})")
                if len(pmf_found) < 3:
                    reasons.append(f"components < 3 ({len(pmf_found)})")
                print(f"  [FAIL] Does NOT meet PMF requirements: {', '.join(reasons)}")

        # Check if data has actual values
        if 'raw_response' in test:
            raw = test['raw_response']
            if 'data' in raw and 'result' in raw['data']:
                result = raw['data']['result']
                if 'resultOne' in result and result['resultOne']:
                    first_record = result['resultOne'][0]
                    # Check if all values are "—" (empty)
                    empty_count = sum(1 for v in first_record.values() if v == '—' or v == '')
                    total_count = len(first_record)
                    print(f"  Data Quality: {empty_count}/{total_count} fields are empty ('—')")

if __name__ == "__main__":
    analyze_pmf_requirement()
