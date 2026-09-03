# Report Chart Reference Index

`create_report_chart` uses two reference layers only:

1. Read this common contract once for the chart task.
2. After selecting `chart_type`, read exactly one matching chart document below.

No additional common reference is required; all other reference files are
single-chart specifications selected by the routing table below.

## Common Contract

- Supply at least one of `data` or `file_path`. When both are present, inline
  `data` is rendered and `file_path` is retained only for provenance.
- `data` is a simple chart data object, not an ECharts option. General charts do
  not infer arbitrary record fields; prepare the exact structure documented for
  the selected chart type.
- Use only an authorized absolute `file_path` returned by an upstream tool in
  the current session. Never guess storage paths. The tool loads it through the
  execution context, so the Agent does not need to read it again.
- For CSV, Excel, or unprepared records, first use `execute_python` to prepare
  and save the target chart structure. Domain chart documents explicitly state
  when raw `records` are supported.
- Titles must be semantic only. Do not include `图1`, `Figure 1`, `1.` or other
  numbering; captions and ordering are assembled by the report layer.
- Word is the default output context. The renderer owns A4 sizing, fonts, label
  thinning, overlap handling, and legend layout; the Agent need not choose these.
- Generate one main chart per image. For dashboards, subplots, or several
  analyses, make separate chart calls unless a documented chart type combines
  the series directly.

## General Chart Routing

- Bar chart or category ranking: read `bar-chart.md`.
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
- Bar-line combination, dual-axis bar-line chart, or stacked bars with a trend:
  read `combo-chart.md`.
- Confidence interval, target range, min/max band, or error bars: read
  `range-and-error.md`.
- Sequential increase/decrease contribution bridge: read `waterfall-chart.md`.
- Ranked contributors with cumulative share: read `pareto-chart.md`.
- Positive/negative comparison or discrete step changes: read
  `comparison-charts.md`.

## Domain Chart Routing

- Guangdong Province AQI calendar only: read `aqi-calendar.md`.
- Calendar for another region/station or a non-AQI pollutant: read
  `pollutant-calendar.md`.
- Generic wind rose, pollutant wind rose, pollution rose, or wind-direction
  concentration chart outside Guangdong-specific reports: read
  `generic-pollutant-wind-rose.md`.
- Guangdong Province pollutant wind rose only: read `pollutant-wind-rose.md`
  and use `chart_type: "pollutant_wind_rose"`.
- Wind direction, wind speed, and one pollutant changing over time: read
  `wind-timeseries.md` and use `chart_type: "wind_timeseries"`.
- Five-element weather forecast time series (wind arrows, speed, temperature,
  precipitation probability, humidity): read `weather-timeseries.md` and use
  `chart_type: "weather_timeseries"`. This type is single-day and must not
  overlay pollution series or data from different dates.

Use `create_report_chart` for formal report images. Use `execute_python` only
for upstream data preparation or cases that require arbitrary Python beyond the
documented chart contracts.

Only pollution-aware chart types may overlay pollutant data on meteorological
backgrounds. Do not use `weather_timeseries` for such overlays.
