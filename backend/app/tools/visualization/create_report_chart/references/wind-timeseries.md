# Wind And Pollutant Time-Series Design

Use `wind_timeseries` for one shared-time-axis report image containing east and
north wind components, wind vectors, wind speed, and one pollutant concentration
series. This is a scientific time-series chart, not a wind rose.

## Data Contract

Preferred arrays using meteorological wind direction in degrees (the direction
the wind comes from, clockwise from north):

```json
{
  "timestamps": ["2026-01-01 00:00", "2026-01-01 01:00"],
  "wind_speeds": [2.1, 3.0],
  "wind_directions": [45, 90],
  "concentrations": [35, 42],
  "wind_direction_convention": "meteorological_from"
}
```

Prepared east/north components may be supplied instead of speed/direction:

```json
{
  "timestamps": ["2026-01-01 00:00", "2026-01-01 01:00"],
  "east_u": [-1.5, -3.0],
  "north_v": [-1.5, 0.0],
  "concentrations": [35, 42]
}
```

Raw records are also supported. Common field names are detected, or specify
fields explicitly:

```json
{
  "records": [
    {"time": "2026-01-01 00:00", "ws": 2.1, "wd": 45, "PM2.5": 35}
  ],
  "time_field": "time",
  "wind_speed_field": "ws",
  "wind_direction_field": "wd",
  "concentration_field": "PM2.5"
}
```

## Design Rules

- Use one pollutant per image and set `pollutant_name` and `unit` in options.
- Timestamps and all measurement arrays must have equal lengths.
- The tool never assumes a wind-direction convention. When speed/direction
  angles are supplied, `wind_direction_convention` is required. Use
  `meteorological_from` for clockwise degrees from north describing where wind
  comes from, or `mathematical_to` for counterclockwise degrees from east
  pointing toward motion.
- When `east_u` and `north_v` are supplied, they are plotted unchanged and no
  direction convention is inferred.
- Wind vectors are automatically thinned when the series is dense. Use
  `max_vectors` only when a specific arrow density is required.
- Do not include figure numbers in the chart title.

## Useful Options

- `pollutant_name` (default `PM2.5`)
- `unit` (default `μg/m³`)
- `wind_speed_unit` (default `m/s`)
- `wind_direction_convention`
- `max_vectors` (default `80`, range `12-160`)
