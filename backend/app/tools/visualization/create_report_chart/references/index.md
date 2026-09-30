# Business Chart Reference Index

`create_business_chart` uses two reference layers only:

1. Read this common contract once for the chart task.
2. After selecting `chart_type`, read exactly one matching chart document below.

No additional common reference is required; all other reference files are
single-chart specifications selected by the routing table below.

## Common Contract

- Supply at least one of `data` or `file_path`. When both are present, inline
  `data` is rendered and `file_path` is retained only for provenance.
- `data` is a simple chart data object, not an ECharts option. Business charts do
  not infer arbitrary record fields; prepare the exact structure documented for
  the selected chart type.
- Use only an authorized `file_path` returned by an upstream tool in
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
  the series directly. Nested `charts` requests are not accepted.
- This tool only accepts the six business types below. Generic bar, line,
  scatter, distribution, correlation and combination charts are not supported.
  Use `execute_echarts_python` for query-mode interactive charts and
  `execute_python` for static analysis and report charts.
- Wind roses require real pollutant concentrations. For pure wind-frequency
  roses, use `execute_python`; never invent placeholder concentrations.

## Domain Chart Routing

- Guangdong Province AQI calendar only: read `aqi-calendar.md`.
- Calendar for another region/station or a non-AQI pollutant: read
  `pollutant-calendar.md`.
- Pollutant wind rose, pollution rose, or wind-direction
  concentration chart outside Guangdong-specific reports: read
  `generic-pollutant-wind-rose.md`.
- Guangdong Province pollutant wind rose only: read `pollutant-wind-rose.md`
  and use `chart_type: "pollutant_wind_rose"`.
- Wind direction, wind speed, and one pollutant changing over time: read
  `wind-timeseries.md` and use `chart_type: "wind_timeseries"`.
- Five-element weather forecast time series (wind arrows, speed, temperature,
  precipitation probability, humidity): read `weather-timeseries.md` and use
  `chart_type: "weather_timeseries"`. This type supports 1–7 consecutive days
  on a continuous time axis. Do not overlay pollutants or overlap daily curves.

Use `execute_python` as the primary static chart tool for analysis and formal
reports, with the shared report theme. Use `create_business_chart` for specific
business chart types and fixed templates that match the documented contracts.
Query mode primarily uses `execute_echarts_python`; business chart templates
are supplementary. Expert and report modes primarily use `execute_python`.
Choose analytical dimensions before selecting a chart; use Python for custom
combinations, facets and multi-panel comparisons.

Only pollution-aware chart types may overlay pollutant data on meteorological
backgrounds. Do not use `weather_timeseries` for such overlays.
