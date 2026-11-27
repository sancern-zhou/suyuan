# Xuchang District Map

Use `chart_type: "xuchang_district_map"` (xuchang project only) for a static
report map of Xuchang's 9 business districts. Pass `records` with `district`
and a numeric `value` (or `districts` plus `values`); set `metric` to `AQI`,
`PM2.5`, `PM10`, `O3`, `NO2`, `SO2`, or `CO`.

District naming follows the station-catalog scope: the 6 official
administrative regions (魏都区/建安区/鄢陵县/襄城县/禹州市/长葛市, matched by
name suffix or adcode) are rendered as choropleth polygons from the versioned
`assets/xuchang_district_boundaries.geojson`, or an inline GeoJSON
FeatureCollection supplied in `data.geojson`/`options.geojson`. The 3
functional zones (东城区/开发区/示范区; aliases 经济技术开发区 and
许昌市城乡一体化示范区 are accepted) have no official administrative boundary,
so they are represented by their catalog station markers (colored by the zone
value) instead of polygons; the renderer draws a footnote explaining this.
Districts without a provided value are outlined as no-data areas.

The default AQI classes are 0-50, 51-100, 101-150, 151-200, 201-300, and >300
with colors matching the national air-quality legend; pollutant metrics use
the HJ 633-2026 concentration breakpoints. Real polygon or station matches are
required: the renderer fails clearly when the asset or district match is
missing and never substitutes schematic shapes.
