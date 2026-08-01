# Combo Chart

Use `combo` for formal-report charts that overlay bars and lines on one shared
categorical x-axis. It covers single-axis and dual-axis bar-line charts,
grouped bars with trends, and stacked bars with trends.

```json
{
  "labels": ["Q1", "Q2", "Q3", "Q4"],
  "series": [
    {"name": "销售额", "type": "bar", "values": [120, 150, 180, 210]},
    {"name": "增长率", "type": "line", "axis": "right", "values": [8.2, 12.5, 9.6, 15.1]}
  ]
}
```

When a right axis is used, provide meanings for both axes with
`left_y_label`/`left_unit` and `right_y_label`/`right_unit`. Only `bar` and
`line` are valid series types. Series with the same non-empty `stack` value
are stacked. Prefer at most four series; six is the hard limit.

Do not use `combo` for several unrelated plots, a third y-axis, or arbitrary
ECharts/Matplotlib configuration. Split unrelated views into separate images.

Invalid examples include a line series with `stack`, more than six series, or
a right-axis series without meanings for both y-axes. Typical errors are
`combo.series[1].stack 仅适用于 bar 系列` and
`combo 使用 right 轴时必须提供左右轴标题或单位`. Dense bar slots and a
left/right magnitude ratio of at least 100 return `combo_narrow_bars` and
`combo_dual_axis_scale_disparity` warnings respectively.
