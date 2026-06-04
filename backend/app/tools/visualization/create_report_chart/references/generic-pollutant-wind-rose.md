# Generic Pollutant Wind Rose Design

Use `generic_pollutant_wind_rose` for wind rose, pollutant wind rose, pollution
rose, or pollutant concentration by wind direction outside Guangdong-specific
report templates. Do not use the Guangdong-specific `pollutant_wind_rose`
outside Guangdong reports.

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

