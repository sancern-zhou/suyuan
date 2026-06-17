# Histogram Design

Use `histogram` for pollutant concentration frequency distribution,
hourly/daily value distribution, or quick distribution checks in reports.

## Data Contract

```json
{
  "values": [12, 14, 18, 21, 35, 42, 45, 47, 55, 60]
}
```

Use raw numeric samples. Do not pass an ECharts histogram option.

## Design Rules

- Put pollutant and unit in `options.x_label`.
- Put `频次` or another count label in `options.y_label`.
- Choose `options.bins` only when the bin count is meaningful; otherwise let
  the renderer use an automatic bin strategy.
- Do not include figure numbers in the chart title.

## Useful Options

- `bins`
- `x_label`
- `y_label`
- `unit`

