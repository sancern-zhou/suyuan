# Chart Types Overview

Use this overview only when deciding which simple chart type to call. After
choosing a type, read the specific design document for that type.

Supported general `chart_type` values:

- `bar` and `horizontal_bar`: read `bar-chart.md`.
- `line` and `timeseries`: read `line-chart.md`.
- `stacked_area`: read `stacked-area.md`.
- `dual_axis_line`: read `dual-axis-line.md`.
- `stacked_bar` and `percent_stacked_bar`: read `stacked-bar.md`.
- `scatter`: read `scatter-chart.md`.
- `pie`: read `pie-rules.md`.
- `histogram`: read `histogram.md`.
- `correlation_heatmap`: read `correlation-heatmap.md`.
- `boxplot`: read `boxplot.md`.
- `table_image`: read `table-image.md`.
- `combo`: read `combo-chart.md`.
- `range_line` and `error_bar`: read `range-and-error.md`.
- `waterfall`: read `waterfall-chart.md`.
- `pareto`: read `pareto-chart.md`.
- `diverging_bar` and `step_line`: read `comparison-charts.md`.
- `pollutant_calendar`: read `pollutant-calendar.md`.
- `generic_pollutant_wind_rose`: read `generic-pollutant-wind-rose.md`.
- `aqi_calendar`: Guangdong Province only; read `aqi-calendar.md`.
- `pollutant_wind_rose`: Guangdong Province only; read `pollutant-wind-rose.md`.

`create_report_chart` data is not an ECharts option. Do not pass `xAxis`,
`yAxis`, or full ECharts `series` objects. Data should be simple and explicit:
use arrays such as `labels`, `values`, `x`, `y`, `series`, or table rows and
columns.

Common environmental-analysis charts already covered by this tool:

- 环比/同比对比柱状图: `bar` with multi-series grouped bars.
- 堆叠面积图: `stacked_area`.
- 双轴折线图: `dual_axis_line`.
- 堆叠柱状图: `stacked_bar`.
- 百分堆叠柱状图: `percent_stacked_bar`.
- 散点图: `scatter`.
- 直方图/频次分布图: `histogram`.
- 柱线组合或双轴柱线: `combo`.
- 置信区间、上下限或误差: `range_line` or `error_bar`.
- 增减因素拆解: `waterfall`.
- 排名与累计贡献率: `pareto`.
- 正负变化对比: `diverging_bar`.
- 离散阶段变化: `step_line`.
- 通用污染物日历图: `pollutant_calendar`.
- 通用风玫瑰图/污染物风玫瑰图: `generic_pollutant_wind_rose`.
- 广东省专用 AQI 日历图: `aqi_calendar`.
- 广东省专用污染物风玫瑰图: `pollutant_wind_rose`.

Common options:

- `x_label`: x-axis label.
- `y_label`: y-axis label.
- `unit`: appended to the y-axis label.
- `legend`: `true` or `false`; multi-series charts show legends by default.
- `reference_lines`: list of reference lines, for example
  `[{"axis": "y", "value": 100, "label": "参考线"}]`.
