# Report Chart Reference Index

Read this file first, then read only the documents needed for the requested
chart. The tool schema is compact on purpose; detailed chart design rules live
in these progressive reference files.

## Data Input

- Read `data-input.md` before the first call or whenever choosing between
  inline `data` and a DataRegistry `data_id`.
- The tool does not accept a file path as chart data input.

## Always Read For Reports

- `word-a4-rules.md`: required for Word or QMD report images.
- `layout-rules.md`: required when the user asks for multiple views, subplots,
  dashboards, comparisons, or several metrics in one request.
- Chart titles passed to `create_report_chart` must be semantic titles only.
  Do not include figure numbers or ordering prefixes such as `图1`, `图2：`,
  `Figure 1`, or `1.`; numbering belongs to the report caption/body assembly
  layer, not the chart image.

## General Chart Routing

- Bar chart or category ranking: read `bar-chart.md`.
- Long category labels: read `long-label-rules.md` after `bar-chart.md`.
- Line chart, trend chart, or time series: read `line-chart.md`.
- Stacked area chart: read `stacked-area.md`.
- Dual-axis line chart: read `dual-axis-line.md`.
- Stacked bar or 100% stacked bar chart: read `stacked-bar.md`.
- Scatter chart or x-y relationship: read `scatter-chart.md`.
- Histogram or frequency distribution chart: read `histogram.md`.
- Correlation matrix or pollutant relationship heatmap: read
  `correlation-heatmap.md`.
- Pollutant distribution, concentration spread, or station distribution box
  plot: read `boxplot.md`.
- Pie or share chart: read `pie-rules.md`.
- Table rendered as an image: read `table-image.md`.
- Bar-line combination, dual-axis bar-line chart, or stacked bars with a trend:
  read `combo-chart.md`.
- Confidence interval, target range, min/max band, or error bars: read
  `range-and-error.md`.
- Sequential increase/decrease contribution bridge: read `waterfall-chart.md`.
- Ranked contributors with cumulative share: read `pareto-chart.md`.
- Positive/negative comparison or discrete step changes: read
  `comparison-charts.md`.
- Unsure which simple chart type to use: read `chart-types.md`.

## Domain Chart Routing

- AQI calendar or monthly daily air-quality calendar: read `aqi-calendar.md`.
- Generic pollutant calendar for any non-Guangdong region, station, or
  non-AQI pollutant: read `pollutant-calendar.md`.
- Generic wind rose, pollutant wind rose, pollution rose, or wind-direction
  concentration chart outside Guangdong-specific reports: read
  `generic-pollutant-wind-rose.md`.
- Guangdong Province AQI calendar only: read `aqi-calendar.md` and use
  `chart_type: "aqi_calendar"`.
- Guangdong Province pollutant wind rose only: read `pollutant-wind-rose.md`
  and use `chart_type: "pollutant_wind_rose"`.

Use `create_report_chart` for formal report images. Use `execute_python` only
for upstream data preparation or cases that require arbitrary Python beyond the
documented chart contracts.
