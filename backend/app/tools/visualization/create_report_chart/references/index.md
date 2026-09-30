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
- Environmental figures must explain colors and symbols with a legend,
  colorbar or direct labels. Series legends normally go below the plot.
  AQI/IAQI grade colors follow HJ 633-2026 appendix A, shared with Python's
  `app.utils.environment_charts`; do not replace them with theme series colors.
  Concentration grades require pollutant-specific averaging periods and
  breakpoints, and are distinct from GB 3095 compliance limits.
  Where a limit is applicable, label its standard, phase, grade, averaging
  period, value and unit. Do not judge hourly compliance against daily limits.
  Missing values are not zero; distinguish forecasts from observations.

## Domain Chart Routing

- Guangdong Province AQI calendar only (Guangdong/default project only): read
  `aqi-calendar.md`. Other projects do not expose this type.
- Calendar for another region/station or a non-AQI pollutant: read
  `pollutant-calendar.md`.
- Pollutant wind rose, pollution rose, or wind-direction
  concentration chart outside Guangdong-specific reports: read
  `generic-pollutant-wind-rose.md`.
- Guangdong Province pollutant wind rose only: read `pollutant-wind-rose.md`
  and use `chart_type: "pollutant_wind_rose"`.
  Other projects do not expose this type; use `generic_pollutant_wind_rose`.
- Wind direction, wind speed, and one pollutant changing over time: read
  `wind-timeseries.md` and use `chart_type: "wind_timeseries"`.
- Five-element weather forecast time series (wind arrows, speed, temperature,
  precipitation probability, humidity): read `weather-timeseries.md` and use
  `chart_type: "weather_timeseries"`. This type supports 1–7 consecutive days
  on a continuous time axis. Do not overlay pollutants or overlap daily curves.
- Henan province city-level AQI or pollutant map: read `henan-city-map.md` and
  use `chart_type: "henan_city_map"`.

First match the six supported business types. In every mode, these types MUST
use `create_business_chart`; do not reimplement their templates in Python or
ECharts. This requirement takes precedence over mode defaults. Python may
prepare input data, and report compositions may reuse business chart images.
For other general or custom types, query mode primarily uses
`execute_echarts_python`; expert and report modes primarily use `execute_python`
with the shared report theme.
Choose analytical dimensions before selecting a chart; use Python for custom
combinations, facets and multi-panel comparisons.

Only pollution-aware chart types may overlay pollutant data on meteorological
backgrounds. Do not use `weather_timeseries` for such overlays.
