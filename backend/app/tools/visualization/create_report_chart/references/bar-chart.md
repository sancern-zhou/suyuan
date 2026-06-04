# Bar Chart Design

Use `bar` for short category comparisons and rankings. Use `horizontal_bar`
when category labels are long, when there are many categories, or when values
need to be scanned as a ranked list.

## Data Contract

Preferred single-series data:

```json
{"labels": ["A", "B"], "values": [12, 18]}
```

Single-series data may also use:

```json
{"labels": ["A", "B"], "series": [{"name": "value", "data": [12, 18]}]}
```

Grouped bar data:

```json
{
  "labels": ["PM2.5", "PM10", "O3"],
  "series": [
    {"name": "2025", "values": [31, 63, 202]},
    {"name": "2026", "values": [18, 45, 169]}
  ]
}
```

## Design Rules

- Keep category labels short for vertical bars.
- Use `horizontal_bar` for long labels instead of rotating dense x labels.
- Use grouped bars for two to four comparable series.
- Use grouped bars for pollutant同比、环比、同环比对比. Put periods in
  `series[].name` and pollutants/metrics in `labels`; do not create a custom
  chart type for this case.
- Split the chart when grouped bars create unreadable legends or labels.
- Put units in `options.y_label` or `options.unit`, not inside every label.

## Useful Options

- `x_label`
- `y_label`
- `unit`
- `legend`
- `reference_lines`
