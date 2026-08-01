# Comparison Charts

## Diverging Bar

Use `diverging_bar` for positive/negative change, improvement/deterioration,
or deviation from a baseline.

```json
{"labels": ["城市A", "城市B", "城市C"], "values": [-8.2, 3.1, -1.5]}
```

`orientation` accepts `auto`, `horizontal`, or `vertical`. Auto mode uses a
horizontal layout for long or numerous labels. The applied orientation is
returned in metadata. Invalid orientation names are rejected.

## Step Line

Use `step_line` when values change at discrete boundaries: policy stages,
standards, tariffs, or operating states. It accepts the normal line-chart
single-series or multi-series data contract. `step` accepts `pre`, `mid`, or
`post` and defaults to `post`.

Do not use a step line merely to decorate a continuous trend; use `line` for
continuous measurements.

`step` values outside `pre`, `mid`, and `post` are invalid and return a precise
options-field error.
