# Waterfall Chart

Use `waterfall` to explain how sequential increases and decreases bridge an
initial value to a final value, such as同比变化贡献、预算变化或排放增减因素。

```json
{
  "labels": ["结构调整", "产量变化", "治理措施"],
  "values": [-12, 8, -6],
  "start_value": 100,
  "show_total": true
}
```

Input order is semantic and is never sorted. `start_value` is optional and
defaults to zero for calculation; when explicitly provided it is drawn as an
initial bar. `show_total` defaults to true. Use `start_label` and `total_label`
in options only when the default labels are unsuitable.

For explicit subtotals, provide a `measures` array aligned with `labels`.
Allowed values are `relative`, `subtotal`, and `total`. Relative values are
increments; subtotal and total values are absolute levels and reset the running
baseline. When the final measure is `total`, no duplicate automatic total is
added.

The lengths of `labels`, `values`, and optional `measures` must match. Unknown
measure names are rejected rather than interpreted silently.
