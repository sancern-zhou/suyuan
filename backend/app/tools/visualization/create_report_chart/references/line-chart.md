# Line Chart Design

Use `line` for ordered trends, daily changes, hourly changes, and time series.
Use `timeseries` only as an alias when the intent is clearly a line trend.

## Data Contract

Single-series trend:

```json
{"labels": ["05-01", "05-02"], "values": [82, 49]}
```

Single-series data may also use:

```json
{"x": ["05-01", "05-02"], "y": [82, 49]}
```

Multi-series trend:

```json
{
  "labels": ["05-01", "05-02"],
  "series": [
    {"name": "AQI", "values": [82, 49]},
    {"name": "O3_8H", "values": [138, 97]}
  ]
}
```

## Design Rules

- Prefer one to three lines per image.
- Use reference lines for standards, targets, or alert thresholds.
- Use stable date labels such as `05-01`; avoid long timestamp strings unless
  the chart has very few points.
- For Word/QMD report images, do not draw every x-axis date label when a daily
  series has many points. The renderer should thin dense x-axis labels to about
  12 readable ticks and return a `dense_x_tick_labels_thinned` warning.
- Split into multiple images when lines use incompatible units or scales.
- Do not pass ECharts `xAxis`, `yAxis`, or full ECharts `series` objects.

## Useful Options

- `x_label`
- `y_label`
- `unit`
- `legend`
- `reference_lines`
