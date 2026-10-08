# Wind Rose Design

Use `wind_rose` for a pure meteorological wind rose. It shows wind-direction
frequency stacked by wind-speed bins and must not receive or invent pollutant
concentrations.

Pass equal-length `wind_directions` and `wind_speeds` arrays, or records with
standard wind aliases. Use `wind_direction_field` and `wind_speed_field` when
record fields differ.

Use `generic_pollutant_wind_rose` only when every observation also has a real
pollutant concentration. Never fill a missing concentration with a constant.

Options: `direction_bins` (default 16) and optional `speed_bins` as
`[[label, lower, upper], ...]` in m/s.
