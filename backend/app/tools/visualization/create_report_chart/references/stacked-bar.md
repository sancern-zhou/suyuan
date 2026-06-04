# Stacked Bar Design

Use `stacked_bar` for absolute component totals by category or period. Use
`percent_stacked_bar` when each category should be normalized to 100%.

## Data Contract

```json
{
  "labels": ["2026年4月", "2026年5月"],
  "series": [
    {"name": "PM2.5", "values": [27, 18]},
    {"name": "PM10", "values": [57, 45]},
    {"name": "O3_8H", "values": [151, 169]}
  ]
}
```

Use at least two `series` entries. Each series length must match `labels`.

## Design Rules

- Use `stacked_bar` when absolute totals matter.
- Use `percent_stacked_bar` when composition percentage matters more than
  absolute magnitude.
- Use regular grouped `bar` for simple同比、环比 comparison where each series
  should be compared side by side.
- Do not include figure numbers in the chart title.

## Useful Options

- `x_label`
- `y_label`
- `unit`
- `legend`

