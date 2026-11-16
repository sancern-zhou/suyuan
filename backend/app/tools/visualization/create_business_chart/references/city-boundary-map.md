# City Boundary Map

Use `chart_type: "city_boundary_map"` for a static report choropleth of any
set of Chinese cities (prefecture-level units; the four municipalities
Beijing/Tianjin/Shanghai/Chongqing each render as one unit). Pass `records`
with `adcode` (preferred, e.g. 320100) or `city` name plus a numeric `value`,
or `cities` plus `values`; set `metric` to `AQI`, `PM2.5`, `PM10`, `O3`,
`NO2`, `SO2`, or `CO`, or supply `options.breaks` (5 ascending thresholds)
for any other measure. The renderer loads the versioned
`assets/china_city_boundaries.geojson` (rebuild with
`provision_boundaries.py`, offline asset, no runtime download) by default, or
uses an inline GeoJSON FeatureCollection supplied in
`data.geojson`/`options.geojson`. Records match by `adcode` first, then by
city name without the trailing "市"; unmatched records are reported in
warnings and metadata, then skipped. The viewport auto-fits to the matched
cities and labels sit on the boundary centroid, so no hand-written city
center table is needed. Optional grouping: set `group` on records (for
example 核心/近场 rings); the first group gets thick dark borders and bold
labels, and a group legend appears when two or more groups exist.
`options.group_order` fixes the group order; `options.star_adcode` marks one
center city with a star. Optional interpolated-surface mode: set
`options.render_mode: "idw"` to paint a smooth IDW field from the city
centroid sample points instead of solid polygon fills (requires at least 8
valid cities; the field is painted with a continuous color ramp anchored on
the six HJ 633 class colors (smooth transitions between class anchor values,
no hard band edges), clipped to the union of the data-city polygons by
default (`options.idw_clip: "cities"` — areas outside the target cities stay
white so extrapolation is never mistaken for data) or to all land in the
viewport (`options.idw_clip: "land"`, coastline-precise like mainstream AQI
maps; unlisted cities inside the view are interpolated extrapolation);
sample dots mark the interpolation seeds and are omitted for cities closer
than 0.25° to a neighbor, which is reported in warnings and metadata). It is
a trend
suggestion, not model-grid or observed data — the image carries a note and
metadata records `render_mode`/`idw` parameters; do not present it as
measured concentrations. Optionally set `options.value_mode: "mid"` to seed
values from record `min`/`max` midpoints (forecast ranges); records without
both bounds fall back to the plain value with a warning. It requires real
city polygon matches and fails clearly when the asset or city match is
missing; it does not substitute schematic shapes. The default AQI classes are
0-50, 51-100, 101-150, 151-200, 201-300, and >300 with colors matching the
national air-quality legend.
