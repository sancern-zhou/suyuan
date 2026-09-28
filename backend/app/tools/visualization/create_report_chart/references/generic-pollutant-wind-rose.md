# Generic Pollutant Wind Rose Design

Use `generic_pollutant_wind_rose` for pollutant concentration by wind direction
outside Guangdong-specific report templates. For a pure meteorological wind
rose with no pollutant, use `wind_rose`. Do not use the Guangdong-specific `pollutant_wind_rose`
outside Guangdong reports. Projects other than the Guangdong default do not
expose `pollutant_wind_rose` at all; always use `generic_pollutant_wind_rose`.

The chart needs wind direction, wind speed and one real pollutant concentration for
the same observation. Wind and pollutant often come from different tools
(weather tools provide wind but no pollutant; air-quality tools provide
pollutant but no wind), so they must be reconciled before calling:

1. Run the weather/wind query and the air-quality query.
2. Use `execute_python` to align them by timestamp, then pass prepared arrays
   `wind_directions` / `wind_speeds` / `concentrations` in `data`, or save the
   joined rows with `save_data(...)` and pass that `file_path`.

Field-name caveats:

- Only flat top-level fields are matched. Flatten nested `measurements` first.
- Concentration lookup uses `pollutant_name`; the standardized key is `PM2_5`,
  not `PM2.5`. Prefer passing an explicit `concentration_field` (e.g. `PM10`,
  `PM2_5`) to avoid mismatches.
- Wind aliases matched: `wind_direction_10m`/`wind_direction`/`WD`/`wd`/
  `风向`; `wind_speed_10m`/`wind_speed`/`WS`/`ws`/`风速`.

## Data Contract

Prepared arrays:

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

## Design Rules

- Use one pollutant per image.
- Use `pollutant_name` and `unit` options instead of embedding units in every
  label.
- Use `direction_bins` only when the report needs a specific directional
  resolution.
- Do not include figure numbers in the chart title.

## Useful Options

- `pollutant_name`
- `unit`
- `direction_bins`
- `show_colorbar` (default `false`; set `true` only when the right-side
  concentration color scale is explicitly required)
