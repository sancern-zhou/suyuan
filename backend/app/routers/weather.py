"""
Weather data API routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from app.services.weather_query_service import weather_query_service
from app.db.database import get_db
from app.db.models import ERA5ReanalysisData, WeatherStation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/weather", tags=["weather"])


class WeatherQueryRequest(BaseModel):
    """Weather data query request."""
    lat: float = Field(..., description="Latitude", ge=-90, le=90)
    lon: float = Field(..., description="Longitude", ge=-180, le=180)
    start_time: str = Field(..., description="Start time (ISO format: 2025-10-26T00:00:00)")
    end_time: str = Field(..., description="End time (ISO format)")
    include_pbl: bool = Field(True, description="Include boundary layer height")
    data_source: str = Field("auto", description="Data source: auto/database/api")


class WeatherStationRequest(BaseModel):
    """Request to add a weather station."""
    station_id: str
    station_name: str
    lat: float
    lon: float
    elevation: Optional[float] = None
    province: Optional[str] = None
    city: Optional[str] = None
    station_type: str = "ground"
    has_pbl_observation: bool = False
    has_upper_air: bool = False
    data_provider: str = "manual"
    is_active: bool = True


@router.post("/query", summary="Query weather data")
async def query_weather(request: WeatherQueryRequest) -> Dict[str, Any]:
    """
    Query weather data with intelligent routing.

    The service automatically routes queries to the appropriate data source:
    - Historical data (>3 days): PostgreSQL database
    - Recent data (0-3 days): Cache → Database
    - Forecast data (future): Open-Meteo API (real-time)

    Args:
        request: Weather query parameters

    Returns:
        Weather data in Open-Meteo format with metadata

    Example:
        ```json
        {
          "lat": 23.13,
          "lon": 113.26,
          "start_time": "2025-10-26T00:00:00",
          "end_time": "2025-10-26T23:59:59",
          "include_pbl": true,
          "data_source": "auto"
        }
        ```
    """
    try:
        logger.info(
            "weather_query_request",
            lat=request.lat,
            lon=request.lon,
            start=request.start_time,
            end=request.end_time,
            source=request.data_source
        )

        data = await weather_query_service.get_weather_data(
            lat=request.lat,
            lon=request.lon,
            start_time=request.start_time,
            end_time=request.end_time,
            include_pbl=request.include_pbl,
            data_source=request.data_source
        )

        logger.info(
            "weather_query_success",
            data_source=data.get("data_source"),
            record_count=data.get("record_count", 0)
        )

        return data

    except Exception as e:
        logger.error("weather_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stations", summary="List weather stations")
async def list_stations(
    city: Optional[str] = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    List weather stations with optional filtering.

    Args:
        city: Filter by city name
        is_active: Filter by active status
        db: Database session

    Returns:
        List of weather stations
    """
    try:
        query = select(WeatherStation)

        if city:
            query = query.where(WeatherStation.city == city)

        query = query.where(WeatherStation.is_active == is_active)

        result = await db.execute(query)
        stations = result.scalars().all()

        return {
            "count": len(stations),
            "stations": [
                {
                    "station_id": s.station_id,
                    "station_name": s.station_name,
                    "lat": s.lat,
                    "lon": s.lon,
                    "elevation": s.elevation,
                    "province": s.province,
                    "city": s.city,
                    "station_type": s.station_type,
                    "has_pbl_observation": s.has_pbl_observation,
                    "has_upper_air": s.has_upper_air,
                    "data_provider": s.data_provider,
                    "is_active": s.is_active
                }
                for s in stations
            ]
        }

    except Exception as e:
        logger.error("list_stations_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stations", summary="Add weather station")
async def add_station(
    request: WeatherStationRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Add a new weather station.

    Args:
        request: Station information
        db: Database session

    Returns:
        Created station information
    """
    try:
        # Check if station already exists
        result = await db.execute(
            select(WeatherStation).where(
                WeatherStation.station_id == request.station_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Station {request.station_id} already exists"
            )

        # Create new station
        station = WeatherStation(
            station_id=request.station_id,
            station_name=request.station_name,
            lat=request.lat,
            lon=request.lon,
            elevation=request.elevation,
            province=request.province,
            city=request.city,
            station_type=request.station_type,
            has_pbl_observation=request.has_pbl_observation,
            has_upper_air=request.has_upper_air,
            data_provider=request.data_provider,
            is_active=request.is_active
        )

        db.add(station)
        await db.commit()
        await db.refresh(station)

        logger.info("station_added", station_id=request.station_id)

        return {
            "status": "success",
            "station_id": station.station_id,
            "message": f"Station {station.station_name} added successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("add_station_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="Get database statistics")
async def get_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Get weather data storage statistics.

    Returns:
        Database statistics including record counts and time ranges
    """
    try:
        # ERA5 data statistics
        era5_count_result = await db.execute(
            select(func.count()).select_from(ERA5ReanalysisData)
        )
        era5_count = era5_count_result.scalar()

        # Time range
        time_range_result = await db.execute(
            select(
                func.min(ERA5ReanalysisData.time),
                func.max(ERA5ReanalysisData.time)
            )
        )
        time_range = time_range_result.first()

        # Unique locations
        location_count_result = await db.execute(
            select(func.count(func.distinct(ERA5ReanalysisData.lat + ERA5ReanalysisData.lon)))
        )
        location_count = location_count_result.scalar()

        # Station count
        station_count_result = await db.execute(
            select(func.count()).select_from(WeatherStation)
        )
        station_count = station_count_result.scalar()

        return {
            "era5_data": {
                "total_records": era5_count,
                "unique_locations": location_count,
                "earliest_data": time_range[0].isoformat() if time_range[0] else None,
                "latest_data": time_range[1].isoformat() if time_range[1] else None
            },
            "stations": {
                "total_count": station_count
            }
        }

    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", summary="Health check")
async def weather_service_health(db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """
    Check weather service health.

    Returns:
        Health status
    """
    try:
        # Test database connection
        await db.execute(select(1))

        return {
            "status": "healthy",
            "service": "weather_query_service",
            "database": "connected"
        }

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "weather_query_service",
            "database": "disconnected",
            "error": str(e)
        }
