# GIS Agent Spatial Capability Layer Design

## Purpose

Build the environmental analysis Agent toward a tool-independent GIS architecture. The Agent should express spatial intent once, then execute it through the best available backend without binding the product to one GIS library or service.

The first implementation slice strengthens Python GIS capability and adds concentration interpolation rendering, while preserving the existing DataRegistry and `gisctl` map rendering flow.

## Guiding Principles

- Keep one spatial capability layer. Do not create many unrelated GIS tools with separate contracts.
- Separate analysis from rendering. Spatial tools produce registered data assets; `gisctl` renders those assets.
- Treat spatial task plans as the stable interface. Python, PostGIS, DuckDB Spatial, GDAL, QGIS, Earth Engine, and Web APIs are execution backends, not the Agent's core architecture.
- Validate CRS, units, geometry validity, data coverage, and output ranges before claiming results.
- Prefer existing project patterns: LLM tools, DataRegistry assets, map programs, and visual blocks.

## Current Baseline

The project already has:

- `spatial_analysis`: a spatial-spec based tool with basic operations: buffer, intersect, filter, distance, nearest, aggregate, top_n, and upwind_sector.
- `gisctl`: a map-control tool that creates point, polygon, set-view, and dashboard-layer map programs.
- DataRegistry assets referenced by `data_id`.
- Frontend rendering for point and polygon layers, plus an existing heatmap dashboard layer.
- Python environment support for `shapely`, `pyproj`, `numpy`, `scipy`, `matplotlib`, and `sklearn`.

The project does not currently declare `geopandas`, `rasterio`, `GDAL`, or `PyKrige` as dependencies.

## Target Architecture

The target flow is:

```text
Natural language request
  -> spatial intent
  -> spatial-spec plan
  -> backend selection
  -> execution
  -> validation
  -> DataRegistry assets
  -> gisctl map program / table / image / explanation
```

`spatial_analysis` remains the primary entry point for vector spatial analysis. It becomes the first implementation of the spatial capability layer.

`spatial_interpolation` is introduced as a specialized operation family under the same architecture. It should reuse the same input resolution, validation, asset registration, metadata, and rendering conventions.

## Component Design

### Spatial Core Module

Add a shared spatial core under `backend/app/tools/spatial/` for reusable GIS primitives:

- input loading from inline GeoJSON and DataRegistry assets
- GeoJSON geometry parsing
- coordinate field resolution
- CRS metadata handling
- automatic local metric CRS selection
- geometry validation and repair where safe
- conversion between records, GeoJSON Features, and Shapely geometries
- area and distance helpers
- common result metadata and warnings

This module is internal. Agent-facing schemas stay in LLM tools.

### Enhanced `spatial_analysis`

Upgrade `spatial_analysis` to use `shapely + pyproj` for vector operations.

Initial operations:

- `buffer`: metric buffer using projected coordinates, output polygon assets.
- `distance`: point-to-point, point-to-line, point-to-polygon, line-to-polygon, and polygon-to-polygon distances where inputs allow it.
- `area`: polygon and multipolygon area in square meters and square kilometers.
- `intersect`: robust point/polygon and polygon/polygon intersection.
- `clip`: clip features by polygon or multipolygon.
- `within`, `contains`, `intersects`: predicate filtering.
- existing `filter`, `nearest`, `aggregate`, `top_n`, and `upwind_sector` remain supported.

Outputs continue to register DataRegistry datasets:

- `spatial_point_asset`
- `spatial_line_asset`
- `spatial_polygon_asset`
- `analysis_table_asset`

Each output metadata block should include operation lineage, CRS assumptions, warnings, and geometry type.

### New `spatial_interpolation`

Add one Agent-facing tool for concentration surface analysis. It should not bypass the spatial core.

Supported v1 inputs:

- `data_id`
- longitude field
- latitude field
- value field
- pollutant name
- unit
- optional bounds or mask polygon
- optional grid resolution
- optional method

Supported v1 methods:

- `kriging`: preferred when `PyKrige` is available.
- `idw`: built-in deterministic fallback using `numpy/scipy`.
- `linear`, `cubic`, `nearest`: `scipy.interpolate.griddata` fallback methods.

If the user explicitly requests kriging and `PyKrige` is missing, the tool must not silently substitute another method unless `allow_fallback=true`.

Outputs:

- `interpolation_grid_asset`: grid cells or sampled grid points with interpolated values.
- `contour_polygon_asset` or `contour_line_asset`: contour geometry derived from the interpolation grid where practical.
- static PNG contour image visual using `matplotlib`.
- metadata describing method, parameters, value range, sample count, bounds, warnings, and fallback behavior.

The v1 map path can render contours as polygon/line GeoJSON through `gisctl`. Image overlay on the live map can be added later as a separate renderer extension.

## Data And Validation Rules

All spatial analysis and interpolation should validate:

- required fields exist
- coordinates are numeric and within longitude/latitude bounds
- value fields are numeric where required
- enough observations are present for the requested method
- duplicate coordinates are handled deterministically
- geometry is valid or repaired with a warning
- projected units are meters before area, distance, and buffer calculations
- output value ranges are plausible relative to input value ranges

Interpolation-specific minimums:

- `idw`: at least 3 valid points.
- `linear` and `cubic`: at least 4 valid non-collinear points.
- `kriging`: at least 8 valid points by default, with a warning below 12.

## Dependency Strategy

Use current installed dependencies for v1 base capability:

- `shapely`
- `pyproj`
- `numpy`
- `scipy`
- `matplotlib`

Add `PyKrige` to project dependencies for true kriging. The code should still be structured so the service starts without `PyKrige` in partially updated environments, but kriging calls return a clear dependency error unless fallback is allowed.

Do not require `GeoPandas`, `Rasterio`, or `GDAL` in the first slice. Add them later when the spatial DSL needs tabular geospatial IO, raster algebra, COG/GeoTIFF, or larger workflow support.

## API And Tool Boundary

`spatial_analysis` and `spatial_interpolation` are analysis tools.

`gisctl` is the rendering control tool.

The Agent should generally follow this sequence:

1. Query or create spatial input assets.
2. Run `spatial_analysis` or `spatial_interpolation`.
3. Inspect result metadata and warnings.
4. Use returned `data_id` values with `gisctl`.
5. Explain assumptions and caveats to the user.

## Error Handling

Failures should be structured and actionable:

- `SPATIAL_INPUT_NOT_FOUND`
- `SPATIAL_FIELD_NOT_FOUND`
- `SPATIAL_INVALID_GEOMETRY`
- `SPATIAL_CRS_UNSUPPORTED`
- `SPATIAL_INSUFFICIENT_POINTS`
- `SPATIAL_DEPENDENCY_MISSING`
- `SPATIAL_INTERPOLATION_FAILED`
- `SPATIAL_OUTPUT_EMPTY`

Warnings should not fail the run when the result is still meaningful, but they must be returned in metadata.

## Testing Strategy

Unit tests:

- CRS projection helper selects stable metric CRS.
- area for known polygon returns expected square-meter range.
- distance for known points returns expected meter range.
- buffer output is polygon geometry with plausible area.
- polygon clip/intersection returns expected feature counts and properties.
- interpolation rejects insufficient points.
- IDW interpolation produces a non-empty grid.
- kriging reports missing dependency cleanly when `PyKrige` is absent.

Integration tests:

- `spatial_analysis` registers polygon and table assets.
- `spatial_interpolation` registers grid/contour/image outputs.
- `gisctl` can render polygon outputs generated by spatial tools.

## Non-Goals For V1

- Full PostGIS backend selection.
- DuckDB Spatial backend.
- Rasterio/GDAL raster processing.
- Earth Engine or STAC workflows.
- Live map image overlays.
- QGIS or ArcGIS automation.
- Enterprise-grade variogram modeling UI.

These are future backends or renderer extensions that should attach to the same spatial capability layer.

## Implementation Sequence

1. Add shared spatial core helpers.
2. Add tests for metric CRS, area, distance, buffer, and GeoJSON conversion.
3. Refactor `spatial_analysis` to use the spatial core while preserving existing operation contracts.
4. Add `area`, `clip`, and richer `distance` operations.
5. Add `spatial_interpolation` with IDW/griddata fallback and optional kriging.
6. Add static contour PNG rendering and DataRegistry asset registration.
7. Register the new tool and update tool descriptions.
8. Add integration tests for DataRegistry outputs and `gisctl` rendering compatibility.

## V1 Decisions

- Add `PyKrige` to `requirements.txt` in the implementation slice.
- Generate static filled contour PNGs for report-style rendering.
- Generate contour line GeoJSON for map rendering through `gisctl`.
- Support bounding-box interpolation extents and optional polygon masks in v1.
