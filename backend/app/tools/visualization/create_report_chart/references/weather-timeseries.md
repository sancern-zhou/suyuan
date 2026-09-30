# Weather time series

Use `chart_type: "weather_timeseries"` for a standardized forecast chart.

Pass `data.records` with `forecast_time`, `wind_speed`,
`wind_direction_degrees`, `temperature`, `precipitation_probability`, and
`humidity`. The renderer automatically handles one to seven consecutive calendar
days on one continuous time axis in a single image. No single-day/multi-day
mode parameter is needed. This does not overlay daily curves.
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
Arrows are slim, equal-length symbols centered on a fixed horizontal row near
the top of the plotting area. Their height and length do not encode wind speed
and do not change with the y-axis scale or line width.
Input direction follows the meteorological "from" convention (0° north, 90°
east); the arrow points toward the direction the air moves, i.e. 180° opposite
the reported source direction. It is not quantized to cardinal directions.
Named regions are shaded without overlaying different days. Set
`options.line_width` to a positive number when many lines require a thinner or
thicker stroke.

North wind points down, east wind points left, south wind points up and west
wind points right. This template uses equal-length direction arrows; their
length does not represent wind speed. Wind speed has its own labeled series.
Do not use quantized eight-direction text glyphs or stretch arrow direction
with time/temperature axis scales.
Zero wind speed is shown as a hollow calm-wind circle, without a direction
arrow. Missing direction or speed is not replaced with an invented arrow;
negative wind speed is rejected.
Dense direction arrows are uniformly thinned to leave readable space; all
valid observations remain in the weather curves. Output metadata records
`direction_arrow_count` and `calm_point_count`.

This supported business template must use `create_business_chart` in every
mode. Python may prepare input data, but must not redraw a substitute template.
