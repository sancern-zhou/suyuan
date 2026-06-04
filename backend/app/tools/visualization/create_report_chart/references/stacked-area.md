# Stacked Area Design

Use `stacked_area` for cumulative pollutant contribution over time, component
composition trends, or several related time series where the total matters.

## Data Contract

```json
{
  "labels": ["05-01", "05-02", "05-03"],
  "series": [
    {"name": "PM2.5", "values": [12, 16, 14]},
    {"name": "PM10", "values": [30, 28, 35]},
    {"name": "O3_8H", "values": [80, 95, 120]}
  ]
}
```

Use at least two `series` entries. Each series length must match `labels`.

## Design Rules

- Use when cumulative composition is meaningful.
- Do not use for unrelated metrics with different units; use `dual_axis_line`
  or split charts instead.
- For dense daily labels, the renderer thins x-axis labels for report images.
- Do not include figure numbers in the chart title.

## Useful Options

- `x_label`
- `y_label`
- `unit`
- `legend`

