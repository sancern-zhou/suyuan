# Pollutant Wind Rose Design

Use `pollutant_wind_rose` only for the Guangdong Province pollutant wind rose
style. This is a 广东省专用 chart type routed through `create_report_chart`.
For other provinces, cities, stations, or generic wind-direction pollutant
distribution, use `generic_pollutant_wind_rose`.

## Data Contract

Preferred prepared data:

```json
{
  "wind_directions": [0, 45, 90],
  "wind_speeds": [1.2, 2.4, 3.0],
  "concentrations": [35, 42, 50]
}
```

Raw records may be used when field names are supplied:

```json
{
  "records": [
    {"wd": 0, "ws": 1.2, "PM10": 35}
  ],
  "wind_direction_field": "wd",
  "wind_speed_field": "ws",
  "concentration_field": "PM10"
}
```

When using `file_path`, the tool should load records through the execution
context and extract arrays from the documented fields. Do not ask the Agent to
hard-code dataset file paths.

## Design Rules

- 广东省专用；其他地区不适用，不要泛化使用。
- Use this chart for static Word/QMD report output, not interactive exploration.
- Keep one pollutant per image.
- Use `pollutant_name` and `unit` options instead of embedding units in every
  label.
- Use controlled font scaling and target Word width from the report chart
  renderer.
- If the data has too few valid wind and concentration pairs, fail with a clear
  validation message instead of returning a placeholder image.

## Useful Options

- `pollutant_name`
- `unit`
- `time_resolution`
- `use_six_level`
- `font_scale`
