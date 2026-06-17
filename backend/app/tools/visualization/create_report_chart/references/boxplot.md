# Boxplot Design

Use `boxplot` for pollutant concentration distributions, station concentration
spread, daily/hourly distribution comparison, or outlier inspection in formal
air-quality reports.

## Data Contract

Preferred data:

```json
{
  "groups": [
    {"name": "PM2.5", "values": [12, 14, 18, 21, 35, 42]},
    {"name": "PM10", "values": [30, 36, 45, 52, 65, 80]},
    {"name": "O3_8H", "values": [80, 105, 130, 150, 170, 202]}
  ]
}
```

Alternative data:

```json
{
  "labels": ["PM2.5", "PM10"],
  "values": [[12, 14, 18], [30, 36, 45]]
}
```

Use raw numeric samples. Do not pass prebuilt ECharts boxplot series.

## Design Rules

- Use one group per pollutant, station, or period.
- Keep the number of groups small enough for an A4 report image.
- Put concentration units in `options.y_label` or `options.unit`.
- Do not include figure numbers in the chart title.
- If the user needs detailed outlier interpretation, explain it in report text,
  not as dense annotations inside the chart.

## Useful Options

- `y_label`
- `unit`

