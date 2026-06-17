# Dual-Axis Line Design

Use `dual_axis_line` for two metrics that share x labels but need separate
y-axis scales, such as AQI and O3_8H concentration.

## Data Contract

```json
{
  "labels": ["05-01", "05-02", "05-03"],
  "series": [
    {"name": "AQI", "values": [82, 49, 56], "axis": "left"},
    {"name": "O3_8H", "values": [138, 97, 107], "axis": "right"}
  ]
}
```

Each series length must match `labels`. Use `axis: "left"` or
`axis: "right"`; if omitted, the second series defaults to the right axis.

## Design Rules

- Use only when the two metrics have different units or scales.
- Avoid more than two or three series; split charts if interpretation becomes
  ambiguous.
- Put axis units in `options.left_y_label` and `options.right_y_label`.
- Do not include figure numbers in the chart title.

## Useful Options

- `left_y_label`
- `right_y_label`
- `legend`

