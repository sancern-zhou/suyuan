# Weather time series

Use `chart_type: "weather_timeseries"` for a standardized forecast chart.

Pass `data.records` for **one natural day only** with `forecast_time`, `wind_speed`,
`wind_direction_degrees`, `temperature`, `precipitation_probability`, and
`humidity`. The renderer rejects records spanning multiple dates; call it once
per day for a seven-day report. Field names can be overridden in `options`.

Optional `areas` contains objects with `start`, `end`, `name`, `color`, `alpha`,
and optional `level` (`high`/`medium`/`low`). Use it for risk periods or other
agent-identified regions. `risk_periods` remains an accepted compatibility alias.

The renderer produces one plot with two y-axes: temperature, humidity, and
precipitation probability share the left axis; wind speed uses the right axis.
Wind direction is shown with a true-degree rotated arrow at each observation.
Input direction follows the meteorological "from" convention (0° north, 90°
east); the arrow points toward the direction the air moves, i.e. 180° opposite
the reported source direction. It is not quantized to cardinal directions.
Named regions are shaded without overlaying different days. Set
`options.line_width` to a positive number when many lines require a thinner or
thicker stroke.
