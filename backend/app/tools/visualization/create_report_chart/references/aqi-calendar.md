# AQI Calendar Design

Use `aqi_calendar` only for the Guangdong Province month-level AQI calendar.
This is a 广东省专用 chart type routed through `create_report_chart`, not a
general calendar and not an ECharts calendar option. For other provinces,
cities, stations, or non-AQI pollutants, use `pollutant_calendar`.

## Data Contract

Preferred prepared data:

```json
{
  "year": 2026,
  "month": 5,
  "pollutant": "AQI",
  "city_data_map": {
    "Guangzhou": {"1": 82, "2": 49}
  }
}
```

Raw records may be used when the adapter supports field extraction:

```json
{
  "records": [
    {"city": "Guangzhou", "date": "2026-05-01", "aqi": 82}
  ],
  "year": 2026,
  "month": 5,
  "pollutant": "AQI",
  "cities": ["Guangzhou"]
}
```

When using `data_id`, the tool should load records through the execution
context and apply the same contract. Do not ask the Agent to hard-code dataset
file paths.

## Design Rules

- Use this chart only for one month at a time.
- 广东省专用；其他地区不适用，不要泛化使用。
- Limit the city list to a readable report layout.
- Keep the title short and semantic. Do not add figure numbers such as `图1`
  or `图2`; put numbering, data source, and coverage details in report text.
- The renderer is responsible for report image dimensions, Chinese font
  selection, and color legend placement.

## Useful Options

- `font_scale`
- `cities`
- `pollutant`
- `year`
- `month`
