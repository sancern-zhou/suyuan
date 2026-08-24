# Henan City Map

Use `chart_type: "henan_city_map"` for a static report map of Henan's 18
prefecture-level cities (including Jiyuan). Pass `records` with `city` and a
numeric `value`, or `cities` plus `values`; set `metric` to `AQI`, `PM2.5`,
`PM10`, `O3`, `NO2`, `SO2`, or `CO`. The renderer loads the versioned
`assets/henan_city_boundaries.geojson` by default, or uses an inline GeoJSON
FeatureCollection supplied in `data.geojson`/`options.geojson`. It requires
real city polygon matches and fails clearly when the asset or city match is
missing; it does not substitute schematic shapes. The default AQI classes are
0-50, 51-100, 101-150, 151-200, 201-300, and >300 with colors matching the
national air-quality legend.
