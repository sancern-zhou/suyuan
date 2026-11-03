# Generic Pollutant Wind Rose Design

Use `generic_pollutant_wind_rose` for pollutant wind rose, pollution
rose, or pollutant concentration by wind direction outside Guangdong-specific
report templates. Do not use the Guangdong-specific `pollutant_wind_rose`
outside Guangdong reports.

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

## Radial Metrics

`radial_metric` selects how the direction bins are drawn:

- `mean_concentration` (default): one bar per direction bin; the bar height is
  that bin's mean concentration and the color is the HJ 633 level of the mean.
  Use it when the reader needs the typical concentration from each direction.
- `level_frequency`: stacked frequency rose. Each direction bin stacks the
  HJ 633 level counts, and the radial axis is the share (%) of all valid
  observations that fall in that direction. Use it when the reader needs the
  pollution-level composition of each direction (like a report pollution
  rose). `direction_bins: 36` gives the dense spoke look; `16` is the default.
  Non-finite, negative and missing concentrations are dropped before binning,
  and a direction with no valid observation stays empty. The fixed six-level
  legend still shows the concentration ranges for each level.

Both modes share the compass frame (N/NE/E/SE/S/SW/W/NW, 0° up, clockwise),
the light grid and the dark outer ring. Direction bins are centered on the
compass points, so wind direction 0° sits in the middle of the N sector.

## Design Rules

- Use one pollutant per image.
- Concentrations must come from real pollutant observations. Use
  `execute_python` for pure wind-frequency roses; do not supply placeholder
  concentrations to reuse this template.
- Colors are NOT data-stretched. Both radial metrics use the fixed
  HJ 633-2026 six-level scale resolved from `pollutant_name` (same palette and
  breaks as AQI calendars); a fixed level legend is always drawn below the
  chart. In `mean_concentration` mode each direction bar takes the level color
  of its mean; in `level_frequency` mode the stack segments take the level
  colors.
- `pollutant_name` must be a built-in indicator (AQI, PM2.5, PM10, SO2, NO2,
  CO, O3) so the six-level breaks resolve; other indicators are rejected.
- `unit` must match the standard basis: μg/m³ (mg/m³ for CO); AQI is unitless.
- Use `pollutant_name` and `unit` options instead of embedding units in every
  label.
- Use `direction_bins` only when the report needs a specific directional
  resolution.
- `average_time` selects the IAQI period for the level breaks (default `24h`,
  O3 default `daily_max_8h`); pass e.g. `1h` when coloring hourly
  observations against hourly breaks.
- Do not include figure numbers in the chart title.

## Useful Options

- `pollutant_name`
- `unit`
- `direction_bins`
- `radial_metric`
- `average_time`
