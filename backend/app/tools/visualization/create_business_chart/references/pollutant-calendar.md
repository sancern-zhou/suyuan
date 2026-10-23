# Pollutant Calendar Design

Use `pollutant_calendar` for a generic month-level pollutant calendar for any
province, city, station, or pollutant. This is a business calendar template. Do not
use the Guangdong-specific `aqi_calendar` outside Guangdong AQI calendar
reports.

Daily cells are colored with the fixed HJ 633-2026 six-level scale (AQI plus the
ambient-air basic pollutants); missing days use the shared grey missing color.
The color map is never stretched to the data range.

## Data Contract

Preferred data:

```json
{
  "year": 2026,
  "month": 5,
  "pollutant": "PM2.5",
  "unit": "μg/m3",
  "values": [
    {"date": "2026-05-01", "value": 18},
    {"date": "2026-05-02", "value": 22}
  ]
}
```

`records` may be used with the same `date` and `value` fields. Use one region
or one station per image. `pollutant` accepts `AQI` or an ambient-air basic
pollutant (PM2.5, PM10, O3, SO2, NO2, CO) and defaults to `AQI` when omitted;
other indicators are rejected instead of being colored with a stretched scale.

## Design Rules

- Use one month per image.
- Use one pollutant per image.
- Put region, station, data source, and coverage notes in report text.
- Do not include figure numbers in the chart title.

## Useful Options

- `year`
- `month`
- `pollutant`
- `unit`
- `average_time` (optional; O3 defaults to `daily_max_8h`, others to `24h`)
