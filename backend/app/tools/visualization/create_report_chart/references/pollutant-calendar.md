# Pollutant Calendar Design

Use `pollutant_calendar` for a generic month-level pollutant calendar for any
province, city, station, or pollutant. This is the general chart type. Do not
use the Guangdong-specific `aqi_calendar` outside Guangdong AQI calendar
reports.

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
or one station per image.

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

