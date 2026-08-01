# Range Line And Error Bar

Use `range_line` when the interval itself is meaningful: confidence bounds,
minimum/maximum range, target band, or observed variability.

```json
{
  "labels": ["1月", "2月", "3月"],
  "series": [
    {"name": "月均值", "values": [42, 38, 35], "lower": [35, 31, 29], "upper": [49, 45, 42]}
  ]
}
```

Each point must satisfy `lower <= values <= upper`. Use no more than two range
series in one report chart.

Use `error_bar` for estimates with measurement or sampling error:

```json
{
  "labels": ["A组", "B组", "C组"],
  "series": [{"name": "均值", "values": [12, 15, 11], "errors": [1.2, 1.5, 0.8]}]
}
```

For asymmetric errors, replace `errors` with both `lower_errors` and
`upper_errors`. Error magnitudes must be non-negative. This type renders
points and error bars; it is not a bar-plus-error combination.

Invalid intervals report the exact bound, for example
`range_line.series[0].lower[2] 不得大于 values[2]`. Do not provide only one
side of an asymmetric error or mix `errors` with asymmetric fields.
