"""Shared Xuchang station and regional-city identifiers.

Constants live in the scenario layer because both the hourly-process and the
station-daily exceedance fetchers need them, and fetchers must not import
each other (circular import risk).
"""

from __future__ import annotations

# dat_station_hour still uses historical codes for the six national sites;
# normalize them to the IDs used by the current station catalog and reports.
NATIONAL_SOURCE_TO_CANONICAL = {
    "2398A": "1003A", "3134A": "1005A", "3337A": "1008A",
    "3338A": "1009A", "4180A": "1011A", "4259A": "1012A",
}
NATIONAL_STATION_IDS = (*NATIONAL_SOURCE_TO_CANONICAL,
                        *NATIONAL_SOURCE_TO_CANONICAL.values())
REGIONAL_CITIES = ("郑州市", "开封市", "平顶山市", "漯河市", "周口市", "商丘市", "驻马店市")
