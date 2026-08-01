# Pareto Chart

Use `pareto` to rank contributors and show their cumulative share, such as
重点污染源、问题类型或缺陷原因识别。

```json
{
  "labels": ["来源A", "来源B", "来源C"],
  "values": [45, 30, 25]
}
```

Values must be non-negative and their total must be greater than zero. The
default `sort: "descending"` sorts values before calculating cumulative
percentages; use `sort: "none"` to preserve a meaningful business order. The
right axis is fixed to percentages and an 80% threshold is shown by default.
The applied order and cumulative values are returned in metadata.

Negative values and a zero total are invalid. For example, a zero total returns
`pareto.values 的合计必须大于 0，无法计算累计占比`.
