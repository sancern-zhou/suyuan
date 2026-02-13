"""
Test particulate city to station to code mapping
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.utils.particulate_city_mapper import get_particulate_city_mapper
from app.utils.geo_matcher import get_geo_matcher


def test_shenzhen_mapping():
    """Test Shenzhen city mapping"""

    print("\n" + "=" * 60)
    print("Test: Shenzhen city mapping")
    print("=" * 60)

    location = "深圳"

    # Step 1: City -> Station
    city_mapper = get_particulate_city_mapper()
    station_name = city_mapper.city_to_station_name(location)

    print(f"\nStep 1 - City to Station:")
    print(f"  Input: {location}")
    print(f"  Output: {station_name}")
    print(f"  Status: {'SUCCESS' if station_name else 'FAILED'}")

    if not station_name:
        station_name = location

    # Step 2: Station -> Code
    geo_matcher = get_geo_matcher()
    station_codes = geo_matcher.stations_to_codes([station_name])

    print(f"\nStep 2 - Station to Code:")
    print(f"  Input: {station_name}")
    print(f"  Output: {station_codes[0] if station_codes else 'None'}")
    print(f"  Status: {'SUCCESS' if station_codes else 'FAILED'}")

    if station_codes:
        print(f"\nFinal Result:")
        print(f"  City: {location}")
        print(f"  Station: {station_name}")
        print(f"  Code: {station_codes[0]}")
        print(f"\nAPI Parameters:")
        print(f"  Station={station_name}")
        print(f"  Code={station_codes[0]}")
        print("\nMAPPING SUCCESS!")
        return True
    else:
        print("\nMAPPING FAILED!")
        return False


def test_multiple_cities():
    """Test multiple cities"""

    print("\n" + "=" * 60)
    print("Test: Multiple cities")
    print("=" * 60)

    test_cases = [
        ("深圳", "Shenzhen"),
        ("广州", "Guangzhou"),
        ("东莞", "Dongguan"),
        ("深南中路", "Direct station name"),
    ]

    city_mapper = get_particulate_city_mapper()
    geo_matcher = get_geo_matcher()

    results = []

    for location, desc in test_cases:
        print(f"\n{desc} ({location}):")

        # City -> Station
        station_name = city_mapper.city_to_station_name(location)
        if not station_name:
            station_name = location

        # Station -> Code
        station_codes = geo_matcher.stations_to_codes([station_name])

        if station_codes:
            print(f"  {location} -> {station_name} -> {station_codes[0]} [OK]")
            results.append(True)
        else:
            print(f"  {location} -> {station_name} -> FAILED [ERROR]")
            results.append(False)

    print(f"\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success1 = test_shenzhen_mapping()
    success2 = test_multiple_cities()

    print("\n" + "=" * 60)
    if success1 and success2:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
