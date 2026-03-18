"""
SQLAlchemy models for meteorological data storage.
Designed for PostgreSQL + TimescaleDB.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Date, Index, JSON
from sqlalchemy.sql import func
from app.db.database import Base
from datetime import datetime


class ERA5ReanalysisData(Base):
    """
    ERA5 Reanalysis meteorological data table.

    TimescaleDB hypertable for efficient time-series storage.
    Stores historical weather conditions including boundary layer height.
    """
    __tablename__ = "era5_reanalysis_data"

    # Primary key components
    time = Column(DateTime(timezone=True), primary_key=True, nullable=False, index=True)
    lat = Column(Float, primary_key=True, nullable=False)
    lon = Column(Float, primary_key=True, nullable=False)

    # Surface meteorological variables
    temperature_2m = Column(Float, comment="2m temperature (°C)")
    relative_humidity_2m = Column(Float, comment="2m relative humidity (%)")
    dew_point_2m = Column(Float, comment="2m dew point (°C)")
    wind_speed_10m = Column(Float, comment="10m wind speed (km/h)")
    wind_direction_10m = Column(Float, comment="10m wind direction (°)")
    wind_gusts_10m = Column(Float, comment="10m wind gusts (km/h)")
    surface_pressure = Column(Float, comment="Surface pressure (hPa)")
    precipitation = Column(Float, comment="Precipitation (mm)")
    cloud_cover = Column(Float, comment="Total cloud cover (%)")

    # Radiation and visibility
    shortwave_radiation = Column(Float, comment="Shortwave radiation (W/m²)")
    visibility = Column(Float, comment="Visibility (m)")

    # Boundary layer (critical for dispersion analysis)
    boundary_layer_height = Column(Float, comment="Boundary layer height (m)")

    # Metadata
    data_source = Column(String(50), default="ERA5", comment="Data source identifier")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite indexes for efficient queries
    __table_args__ = (
        Index("idx_era5_location", "lat", "lon", "time"),
        Index("idx_era5_time_desc", "time"),
    )


class ObservedWeatherData(Base):
    """
    Observed weather data from monitoring stations.

    Ground truth measurements from actual weather stations.
    Used for validation and improving accuracy.
    """
    __tablename__ = "observed_weather_data"

    # Primary key components
    time = Column(DateTime(timezone=True), primary_key=True, nullable=False, index=True)
    station_id = Column(String(50), primary_key=True, nullable=False, index=True)

    # Station information
    station_name = Column(String(100), comment="Station name")
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    # Observed meteorological variables
    temperature_2m = Column(Float, comment="2m temperature (°C)")
    relative_humidity_2m = Column(Float, comment="2m relative humidity (%)")
    dew_point_2m = Column(Float, comment="2m dew point (°C)")
    wind_speed_10m = Column(Float, comment="10m wind speed (km/h)")
    wind_direction_10m = Column(Float, comment="10m wind direction (°)")
    surface_pressure = Column(Float, comment="Surface pressure (hPa)")
    precipitation = Column(Float, comment="Precipitation (mm)")
    cloud_cover = Column(Float, comment="Total cloud cover (%)")
    visibility = Column(Float, comment="Visibility (m)")

    # Data quality metadata
    data_source = Column(String(50), comment="Data provider (NOAA_ISD/CMA/API)")
    data_quality = Column(String(20), comment="Quality flag (good/suspect/poor)")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_observed_station", "station_id", "time"),
        Index("idx_observed_time_desc", "time"),
    )


class WeatherStation(Base):
    """
    Weather station metadata.

    Master list of monitoring stations with location and capabilities.
    """
    __tablename__ = "weather_stations"

    station_id = Column(String(50), primary_key=True, comment="Unique station identifier")
    station_name = Column(String(100), nullable=False, comment="Station name")
    lat = Column(Float, nullable=False, comment="Latitude")
    lon = Column(Float, nullable=False, comment="Longitude")
    elevation = Column(Float, comment="Elevation above sea level (m)")

    # Administrative location
    province = Column(String(50), comment="Province/Region")
    city = Column(String(50), comment="City")

    # Station characteristics
    station_type = Column(
        String(50),
        comment="Station type (ground/upper_air/radar)"
    )

    # Observation capabilities
    has_pbl_observation = Column(
        Boolean,
        default=False,
        comment="Has boundary layer height measurements (very rare)"
    )
    has_upper_air = Column(
        Boolean,
        default=False,
        comment="Has radiosonde/upper air observations"
    )

    # Data provider and status
    data_provider = Column(String(50), comment="Data provider (CMA/NOAA/custom)")
    is_active = Column(Boolean, default=True, comment="Station is currently operational")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Spatial index for location-based queries
    # Note: Requires PostGIS extension for spatial indexing
    # geom = Column(Geometry('POINT', srid=4326))
    # __table_args__ = (Index("idx_stations_geom", "geom", postgresql_using="gist"),)


class WeatherDataCache(Base):
    """
    Short-term weather data cache table (optional).

    For frequently accessed recent data to reduce API calls.
    Alternative to Redis for persistence across restarts.
    """
    __tablename__ = "weather_data_cache"

    cache_key = Column(String(255), primary_key=True, comment="Cache key (location_date_params)")
    data_json = Column(String, comment="Cached weather data (JSON)")
    data_type = Column(String(50), comment="Data type (forecast/recent/historical)")

    # Cache metadata
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True, comment="Expiration time")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Index for cleanup of expired entries
    __table_args__ = (Index("idx_cache_expiry", "expires_at"),)


class FireHotspot(Base):
    """
    Fire hotspot data from NASA FIRMS.

    TimescaleDB hypertable for satellite-detected fire/thermal anomalies.
    Used to identify biomass burning as potential pollution sources.
    """
    __tablename__ = "fire_hotspots"

    # Primary key (auto-increment)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Spatial coordinates
    lat = Column(Float, nullable=False, comment="Fire hotspot latitude")
    lon = Column(Float, nullable=False, comment="Fire hotspot longitude")

    # Fire characteristics
    brightness = Column(Float, comment="Brightness temperature (K)")
    frp = Column(Float, comment="Fire Radiative Power (MW)")
    confidence = Column(Integer, comment="Detection confidence (0-100)")

    # Temporal information
    acq_datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Acquisition time (UTC)"
    )

    # Satellite metadata
    satellite = Column(String(20), comment="Satellite identifier (Terra/Aqua/SNPP/NOAA-20)")
    daynight = Column(String(1), comment="Day/Night flag (D/N)")

    # Additional fire parameters
    scan = Column(Float, comment="Scan angle (degrees)")
    track = Column(Float, comment="Track angle (degrees)")
    bright_t31 = Column(Float, comment="Channel 31 brightness temperature (K)")

    # Data source and quality
    data_source = Column(String(50), default="NASA_FIRMS", comment="Data source identifier")
    version = Column(String(20), comment="Data version")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_fire_location", "lat", "lon"),
        Index("idx_fire_time", "acq_datetime"),
        Index("idx_fire_confidence", "confidence"),
        Index("idx_fire_location_time", "lat", "lon", "acq_datetime"),
    )


class DustForecast(Base):
    """
    Dust aerosol forecast data from CAMS.

    TimescaleDB hypertable for dust/sandstorm forecasts.
    Used to identify dust transport events as pollution sources.
    """
    __tablename__ = "dust_forecasts"

    # Primary key (auto-increment)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Spatial coordinates (grid point)
    lat = Column(Float, nullable=False, comment="Grid point latitude")
    lon = Column(Float, nullable=False, comment="Grid point longitude")

    # Temporal information
    forecast_time = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Forecast issue time (UTC)"
    )
    valid_time = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Forecast valid time (UTC)"
    )
    leadtime_hour = Column(Integer, comment="Forecast lead time (hours)")

    # Dust parameters
    dust_aod_550nm = Column(Float, comment="Dust aerosol optical depth at 550nm")
    total_aod_550nm = Column(Float, comment="Total aerosol optical depth at 550nm")
    dust_surface_concentration = Column(Float, comment="Dust surface concentration (μg/m³)")
    dust_column_mass = Column(Float, comment="Dust column mass density (kg/m²)")
    pm10_concentration = Column(Float, comment="PM10 concentration (μg/m³)")

    # Data source and quality
    data_source = Column(String(50), default="CAMS", comment="Data source identifier")
    model_version = Column(String(50), comment="CAMS model version")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_dust_location", "lat", "lon"),
        Index("idx_dust_valid_time", "valid_time"),
        Index("idx_dust_forecast_time", "forecast_time"),
        Index("idx_dust_location_time", "lat", "lon", "valid_time"),
    )


class DustEvent(Base):
    """
    Dust/sandstorm event records.

    Manually identified or algorithmically detected dust events.
    Used for historical analysis and validation.
    """
    __tablename__ = "dust_events"

    # Primary key (auto-increment)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Event identification
    event_name = Column(String(200), comment="Event name or description")
    event_date = Column(DateTime(timezone=True), nullable=False, comment="Event occurrence date")
    event_duration_hours = Column(Integer, comment="Event duration (hours)")

    # Affected region (bounding box)
    min_lat = Column(Float, comment="Minimum latitude of affected region")
    max_lat = Column(Float, comment="Maximum latitude of affected region")
    min_lon = Column(Float, comment="Minimum longitude of affected region")
    max_lon = Column(Float, comment="Maximum longitude of affected region")
    affected_provinces = Column(String, comment="Comma-separated list of affected provinces")

    # Event intensity
    intensity_level = Column(String(20), comment="Intensity level (轻度/中度/重度)")
    max_dust_aod = Column(Float, comment="Maximum dust AOD during event")
    max_pm10_concentration = Column(Float, comment="Maximum PM10 concentration (μg/m³)")
    min_visibility = Column(Float, comment="Minimum visibility (m)")

    # Source information
    source_region = Column(String(200), comment="Source region (e.g., 蒙古国, 塔克拉玛干)")
    transport_direction = Column(String(100), comment="Transport direction (e.g., 西北向东南)")

    # Data source and quality
    data_source = Column(String(50), comment="Data source (CAMS/Manual/Algorithm)")
    confidence_level = Column(String(20), comment="Confidence level (low/medium/high)")
    notes = Column(String, comment="Additional notes")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_dust_event_date", "event_date"),
        Index("idx_dust_event_region", "min_lat", "max_lat", "min_lon", "max_lon"),
    )


class AirQualityForecast(Base):
    """
    Air quality daily forecast table.

    Stores daily air quality forecast data (future 7 days).
    Priority: calculated_aqi (from six pollutants) > aqi (SQL Server forecast).
    """
    __tablename__ = "air_quality_forecast"

    id = Column(Integer, primary_key=True, autoincrement=True)
    forecast_date = Column(Date, nullable=False, index=True, comment="Forecast date")
    source = Column(String(20), nullable=False, comment="Data source: qweather/waqi")

    # Primary AQI fields (calculated from six pollutants)
    calculated_aqi = Column(Integer, comment="AQI calculated from six pollutants (max of IAQI_PM2.5, IAQI_PM10, IAQI_O3, IAQI_SO2, IAQI_NO2, IAQI_CO)")
    calculated_aqi_level = Column(String(20), comment="Calculated AQI level name")
    calculated_primary_pollutant = Column(String(20), comment="Calculated primary pollutant")

    # Fallback AQI fields (from SQL Server)
    aqi = Column(Integer, comment="SQL Server forecast AQI")
    aqi_level = Column(String(20), comment="SQL Server AQI level name")
    aqi_level_value = Column(Integer, comment="SQL Server AQI level value (1-6)")
    primary_pollutant = Column(String(20), comment="SQL Server primary pollutant")

    # Pollutants details
    pollutants = Column(JSON, comment="Pollutant details (JSON format)")

    # Metadata
    update_time = Column(DateTime(timezone=True), nullable=False, comment="Update time")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_forecast_date", "forecast_date"),
        Index("idx_update_time", "update_time"),
        Index("idx_forecast_source", "source"),
        Index("idx_aqi_level_value", "aqi_level_value"),
    )


class CityAQIPublishHistory(Base):
    """
    City hourly air quality monitoring data table.

    Stores historical hourly air quality data for cities.
    Six pollutants: CO, NO2, O3, PM10, PM2_5, SO2 + AQI.

    Note: PostgreSQL table stores columns in lowercase (snake_case).
    """
    __tablename__ = "city_aqi_publish_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time_point = Column(DateTime(timezone=True), nullable=False, index=True, comment="Data time point")
    area = Column(String(50), nullable=False, index=True, comment="City name")
    city_code = Column(Integer, comment="City code")

    # Six pollutant concentrations
    co = Column(Float, comment="CO concentration (mg/m³)")
    no2 = Column(Float, comment="NO2 concentration (μg/m³)")
    o3 = Column(Float, comment="O3 concentration (μg/m³)")
    pm10 = Column(Float, comment="PM10 concentration (μg/m³)")
    pm2_5 = Column(Float, comment="PM2.5 concentration (μg/m³)")
    so2 = Column(Float, comment="SO2 concentration (μg/m³)")

    # AQI data
    aqi = Column(Integer, comment="Air Quality Index")
    primary_pollutant = Column(String(50), comment="Primary pollutant")
    quality = Column(String(20), comment="Air quality level")

    # Metadata
    create_time = Column(DateTime(timezone=True), comment="Record creation time")

    # Indexes
    __table_args__ = (
        Index("idx_city_history_time", "time_point"),
        Index("idx_city_history_area", "area"),
        Index("idx_city_history_area_time", "area", "time_point"),
    )
