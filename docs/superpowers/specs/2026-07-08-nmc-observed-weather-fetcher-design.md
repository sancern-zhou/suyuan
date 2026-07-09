# NMC Observed Weather Fetcher Design

## Goal

Add scheduled ingestion for hourly observed meteorology for Xuchang and Yuncheng, storing the data in the existing `observed_weather_data` table for air pollution source-tracing analysis.

## Source

Use the public NMC city weather endpoint:

- Yuncheng: `https://www.nmc.cn/rest/weather?stationid=AupnI`
- Xuchang: `https://www.nmc.cn/rest/weather?stationid=ZzMTA`

The response contains current real-time values in `data.real` and recent hourly observations in `data.passedchart`. The fetcher will ingest `passedchart` because it provides an hourly time series and allows the next run to backfill recent missed hours.

## Target Table

Store records in the existing `observed_weather_data` table through `WeatherRepository.save_observed_data`, using the existing `(time, station_id)` upsert behavior.

Required table fields are sufficient for the core source-tracing meteorology:

- wind speed
- wind direction
- temperature
- humidity
- pressure
- precipitation
- station metadata

The table does not store weather text, warning text, wind-level text, or apparent temperature. These are not required for the first scheduled ingestion.

## Field Mapping

| NMC field | Target field | Notes |
| --- | --- | --- |
| `passedchart[].time` | `time` | Parse as Asia/Shanghai local observation hour. |
| station code | `station_id` | `AupnI` for Yuncheng, `ZzMTA` for Xuchang. |
| city name | `station_name` | `运城` or `许昌`. |
| configured latitude | `lat` | Yuncheng `35.11`, Xuchang `34.07`. |
| configured longitude | `lon` | Yuncheng `111.06`, Xuchang `113.92`. |
| `temperature` | `temperature_2m` | Celsius. |
| `humidity` | `relative_humidity_2m` | Percent. |
| `pressure` | `surface_pressure` | hPa. Sentinel `9999` becomes `None`. |
| `rain1h` | `precipitation` | Hourly precipitation in mm. Sentinel `9999` becomes `None`. |
| `windDirection` | `wind_direction_10m` | Degrees. |
| `windSpeed` | `wind_speed_10m` | NMC page displays m/s. |
| constant | `data_source` | `NMC`. |
| validation result | `data_quality` | `good` when core values parse, otherwise `partial`. |

All NMC sentinel values such as `9999` and empty strings are normalized to `None`.

## Fetcher Behavior

Create a dedicated `NMCObservedWeatherFetcher` rather than changing the existing Open-Meteo `ObservedWeatherFetcher`.

The fetcher will:

1. Run hourly through the existing `FetcherScheduler`.
2. Fetch both city endpoints.
3. Parse all available `passedchart` rows, normally the latest 24 hours.
4. Upsert each parsed row into `observed_weather_data`.
5. Continue with the other city if one city fetch fails.
6. Return and log counts for fetched, saved, skipped, and failed rows.

The fetcher should be registered in both lifecycle paths that currently register fetchers:

- `backend/app/services/lifecycle_manager.py`
- `backend/app/fetchers/__init__.py`

## Error Handling

Network and malformed-response failures are logged per city. A city-level failure should not abort the whole fetcher unless every city fails. Invalid rows are skipped with a count and should not prevent valid rows from being saved.

## Testing

Add tests before implementation for:

- NMC sentinel normalization.
- Mapping a `passedchart` row into an observed data point.
- Fetcher stores rows for both configured cities and continues if one city fails.
- Fetcher registration includes the new NMC fetcher.

Use mocked HTTP/client responses and a fake repository. Do not rely on live NMC network calls in unit tests.
