# Weather time series

Use `chart_type: "weather_timeseries"` for a standardized forecast chart.

Pass `data.records` with `forecast_time`, `wind_speed`,
`wind_direction_degrees`, `temperature`, `precipitation_probability`, and
`humidity`. By default records must belong to one natural day. Set
`options.multi_day=true` to render up to seven consecutive calendar days on one
continuous time axis in a single image. This does not overlay daily curves.
Multi-day charts use a wider layout, day boundaries and hour ticks. Gaps longer
than `options.expected_interval_hours` (default 3, a finite positive number)
break the curves; missing records are not interpolated. Metadata includes
`multi_day`, `day_count`, `gap_count`, and the original `valid_point_count`.
Field names can be overridden in `options`.

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
