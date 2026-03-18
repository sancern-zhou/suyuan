"""
卫星数据统一接口
集成 Sentinel-5P TROPOMI、MODIS AOD 等卫星数据源
"""

from typing import Dict, Any, List, Optional, Tuple
import structlog
from datetime import datetime, timedelta
import numpy as np

logger = structlog.get_logger()

# 延迟导入earthengine-api，允许在未安装时也能导入其他模块
try:
    import ee
    EARTHENGINE_AVAILABLE = True
except ImportError:
    EARTHENGINE_AVAILABLE = False
    ee = None


class SatelliteDataHub:
    """
    卫星数据统一接口

    支持的数据源:
    - Sentinel-5P TROPOMI: NO2, SO2, CO, HCHO, O3, CH4, AER_AI
    - MODIS: AOD 550nm (Terra + Aqua)
    - VIIRS: AOD 550nm (可选)
    """

    def __init__(self, demo_mode: bool = True, project_id: str = None):
        """
        初始化卫星数据中心

        Args:
            demo_mode: 是否启用演示模式（未认证时返回示例数据）
            project_id: Google Cloud项目ID（可选，工具会自动尝试设置）
        """
        self.initialized = False
        self.ee_available = EARTHENGINE_AVAILABLE
        self.demo_mode = demo_mode
        self.project_id = project_id

        # 自动设置项目ID（如果环境变量存在）
        import os
        if not self.project_id:
            self.project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')

        if not self.ee_available:
            logger.warning(
                "earthengine_not_available",
                error="earthengine-api未安装",
                hint="请运行: pip install earthengine-api"
            )
        else:
            self._initialize_ee()

    def _initialize_ee(self):
        """初始化Google Earth Engine"""
        if not self.ee_available:
            logger.warning("earth_engine_skipped", reason="EARTHENGINE_AVAILABLE=False")
            return

        # 使用项目ID初始化（如果可用）
        init_kwargs = {}
        if self.project_id:
            init_kwargs['project'] = self.project_id
            logger.info(
                "initializing_gee_with_project",
                project_id=self.project_id
            )
        else:
            logger.info("initializing_gee_without_project")

        try:
            ee.Initialize(**init_kwargs)
            self.initialized = True
            logger.info("satellite_data_hub_initialized")
        except Exception as e:
            logger.warning(
                "earth_engine_init_failed",
                error=str(e),
                hint="请运行: earthengine authenticate"
            )
            # 尝试初始化（失败时稍后重试）
            try:
                ee.Initialize(**init_kwargs)
                self.initialized = True
                logger.info("satellite_data_hub_retry_success")
            except Exception as e2:
                logger.error(
                    "earth_engine_final_init_failed",
                    error=str(e2),
                    hint="需要Google Earth Engine认证或未安装earthengine-api"
                )

    async def fetch_satellite_data(
        self,
        data_type: str,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        统一卫星数据获取接口

        Args:
            data_type: 数据类型 (s5p_no2, modis_aod, s5p_so2, s5p_co, s5p_hcho, s5p_o3)
            bbox: 边界框 (min_lat, min_lon, max_lat, max_lon)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            **kwargs: 其他参数

        Returns:
            标准化数据格式
        """
        if not self.initialized:
            # 注意：_initialize_ee() 不是异步方法，直接调用
            self._initialize_ee()

        try:
            if data_type == "s5p_no2":
                return await self._fetch_s5p_no2(bbox, start_date, end_date, **kwargs)
            elif data_type == "modis_aod":
                return await self._fetch_modis_aod(bbox, start_date, end_date, **kwargs)
            elif data_type == "s5p_so2":
                return await self._fetch_s5p_so2(bbox, start_date, end_date, **kwargs)
            elif data_type == "s5p_co":
                return await self._fetch_s5p_co(bbox, start_date, end_date, **kwargs)
            elif data_type == "s5p_hcho":
                return await self._fetch_s5p_hcho(bbox, start_date, end_date, **kwargs)
            elif data_type == "s5p_o3":
                return await self._fetch_s5p_o3(bbox, start_date, end_date, **kwargs)
            elif data_type == "s5p_aer_ai":
                return await self._fetch_s5p_aer_ai(bbox, start_date, end_date, **kwargs)
            else:
                raise ValueError(f"不支持的数据类型: {data_type}")

        except Exception as e:
            logger.error(
                "satellite_data_fetch_failed",
                data_type=data_type,
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e),
                "data_type": data_type
            }

    async def _fetch_s5p_no2(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        cloud_fraction_threshold: float = 0.3
    ) -> Dict[str, Any]:
        """
        获取Sentinel-5P NO2柱浓度数据

        Args:
            bbox: 边界框
            start_date: 开始日期
            end_date: 结束日期
            cloud_fraction_threshold: 云覆盖阈值
        """
        try:
            # 检查EE是否可用和已初始化
            if not self.ee_available or ee is None:
                return {
                    "success": False,
                    "error": "Google Earth Engine未安装。"
                            "请先运行: pip install earthengine-api && earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_INSTALLED"
                }

            # 检查EE是否已初始化（已认证）
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Google Earth Engine未认证。"
                            "请运行: earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_AUTHENTICATED"
                }

            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            # 加载Sentinel-5P NO2数据集
            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2') \
                .filterDate(start_date, end_date) \
                .filterBounds(region) \
                .filter(ee.Filter.lt('CLOUD_FRACTION', cloud_fraction_threshold))

            # 选择NO2柱浓度波段
            no2_band = 'tropospheric_NO2_column_number_density'
            no2_mean = collection.select(no2_band).mean()

            # 获取统计值
            stats = no2_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=5500,  # 5.5km分辨率
                maxPixels=1e9
            ).getInfo()

            # 计算覆盖率
            total_images = collection.size().getInfo()
            valid_images = collection.filter(
                ee.Filter.notNull([no2_band])
            ).size().getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "NO2_column_density",
                "unit": "mol/m2",
                "spatial_resolution": "5.5km",
                "temporal_range": {
                    "start": start_date,
                    "end": end_date
                },
                "bbox": bbox,
                "statistics": stats,
                "image_count": total_images,
                "valid_image_count": valid_images,
                "cloud_threshold": cloud_fraction_threshold,
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            logger.error("s5p_no2_fetch_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _fetch_modis_aod(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        satellites: List[str] = None
    ) -> Dict[str, Any]:
        """
        获取MODIS AOD数据

        Args:
            bbox: 边界框
            start_date: 开始日期
            end_date: 结束日期
            satellites: 卫星列表 ["terra", "aqua"]
        """
        try:
            # 检查EE是否可用和已初始化
            if not self.ee_available or ee is None:
                return {
                    "success": False,
                    "error": "Google Earth Engine未安装。"
                            "请先运行: pip install earthengine-api && earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_INSTALLED"
                }

            # 检查EE是否已初始化（已认证）
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Google Earth Engine未认证。"
                            "请运行: earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_AUTHENTICATED"
                }

            if satellites is None:
                satellites = ["terra", "aqua"]

            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collections = []

            if "terra" in satellites:
                collections.append(
                    ee.ImageCollection('MODIS/061/MOD04_3K')
                    .filterDate(start_date, end_date)
                    .filterBounds(region)
                    .select('Optical_Depth_047')
                )

            if "aqua" in satellites:
                collections.append(
                    ee.ImageCollection('MODIS/061/MYD04_3K')
                    .filterDate(start_date, end_date)
                    .filterBounds(region)
                    .select('Optical_Depth_047')
                )

            # 合并数据
            if len(collections) == 0:
                raise ValueError("没有有效的卫星数据源")

            combined = collections[0]
            if len(collections) > 1:
                for col in collections[1:]:
                    combined = combined.merge(col)

            # 计算均值
            aod_mean = combined.mean()

            # 获取统计值
            stats = aod_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=3000,  # 3km分辨率
                maxPixels=1e9
            ).getInfo()

            # 计算覆盖率
            total_images = combined.size().getInfo()

            return {
                "success": True,
                "data_source": f"MODIS {'+'.join(satellites).title()}",
                "parameter": "AOD_550nm",
                "unit": "dimensionless",
                "spatial_resolution": "3km",
                "temporal_range": {
                    "start": start_date,
                    "end": end_date
                },
                "bbox": bbox,
                "satellites": satellites,
                "statistics": stats,
                "image_count": total_images,
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            logger.error("modis_aod_fetch_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _fetch_s5p_so2(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """获取Sentinel-5P SO2数据"""
        try:
            # 检查EE是否可用和已初始化
            if not self.ee_available or ee is None:
                return {
                    "success": False,
                    "error": "Google Earth Engine未安装。"
                            "请先运行: pip install earthengine-api && earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_INSTALLED"
                }

            # 检查EE是否已初始化（已认证）
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Google Earth Engine未认证。"
                            "请运行: earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_AUTHENTICATED"
                }

            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_SO2') \
                .filterDate(start_date, end_date) \
                .filterBounds(region)

            so2_band = 'SO2_column_number_density_molec/cm2'
            so2_mean = collection.select(so2_band).mean()

            stats = so2_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=5500,
                maxPixels=1e9
            ).getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "SO2_column_density",
                "unit": "molec/cm2",
                "spatial_resolution": "5.5km",
                "temporal_range": {"start": start_date, "end": end_date},
                "bbox": bbox,
                "statistics": stats,
                "image_count": collection.size().getInfo(),
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_s5p_co(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """获取Sentinel-5P CO数据"""
        try:
            # 检查EE是否可用和已初始化
            if not self.ee_available or ee is None:
                return {
                    "success": False,
                    "error": "Google Earth Engine未安装。"
                            "请先运行: pip install earthengine-api && earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_INSTALLED"
                }

            # 检查EE是否已初始化（已认证）
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Google Earth Engine未认证。"
                            "请运行: earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_AUTHENTICATED"
                }

            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CO') \
                .filterDate(start_date, end_date) \
                .filterBounds(region)

            co_band = 'CO_column_number_density'
            co_mean = collection.select(co_band).mean()

            stats = co_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=7000,
                maxPixels=1e9
            ).getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "CO_column_density",
                "unit": "mol/m2",
                "spatial_resolution": "7km",
                "temporal_range": {"start": start_date, "end": end_date},
                "bbox": bbox,
                "statistics": stats,
                "image_count": collection.size().getInfo(),
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_s5p_hcho(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """获取Sentinel-5P HCHO数据"""
        try:
            # 检查EE是否可用和已初始化
            if not self.ee_available or ee is None:
                return {
                    "success": False,
                    "error": "Google Earth Engine未安装。"
                            "请先运行: pip install earthengine-api && earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_INSTALLED"
                }

            # 检查EE是否已初始化（已认证）
            if not self.initialized:
                return {
                    "success": False,
                    "error": "Google Earth Engine未认证。"
                            "请运行: earthengine authenticate",
                    "error_code": "EARTHENGINE_NOT_AUTHENTICATED"
                }

            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_HCHO') \
                .filterDate(start_date, end_date) \
                .filterBounds(region)

            hcho_band = 'tropospheric_HCHO_column_number_density'
            hcho_mean = collection.select(hcho_band).mean()

            stats = hcho_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=5500,
                maxPixels=1e9
            ).getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "HCHO_column_density",
                "unit": "mol/m2",
                "spatial_resolution": "5.5km",
                "temporal_range": {"start": start_date, "end": end_date},
                "bbox": bbox,
                "statistics": stats,
                "image_count": collection.size().getInfo(),
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_s5p_o3(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """获取Sentinel-5P O3数据"""
        try:
            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_O3') \
                .filterDate(start_date, end_date) \
                .filterBounds(region)

            o3_band = 'O3_column_number_density'
            o3_mean = collection.select(o3_band).mean()

            stats = o3_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=5500,
                maxPixels=1e9
            ).getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "O3_column_density",
                "unit": "mol/m2",
                "spatial_resolution": "5.5km",
                "temporal_range": {"start": start_date, "end": end_date},
                "bbox": bbox,
                "statistics": stats,
                "image_count": collection.size().getInfo(),
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_s5p_aer_ai(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """获取Sentinel-5P气溶胶指数数据"""
        try:
            min_lat, min_lon, max_lat, max_lon = bbox
            region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

            collection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_AER_AI') \
                .filterDate(start_date, end_date) \
                .filterBounds(region)

            aer_ai_band = 'aerosol_index_354_388'
            aer_ai_mean = collection.select(aer_ai_band).mean()

            stats = aer_ai_mean.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=5500,
                maxPixels=1e9
            ).getInfo()

            return {
                "success": True,
                "data_source": "Sentinel-5P TROPOMI",
                "parameter": "aerosol_index",
                "unit": "dimensionless",
                "spatial_resolution": "5.5km",
                "temporal_range": {"start": start_date, "end": end_date},
                "bbox": bbox,
                "statistics": stats,
                "image_count": collection.size().getInfo(),
                "schema_version": "v2.0",
                "generator": "satellite_data_hub"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_available_data_types(self) -> List[Dict[str, Any]]:
        """
        获取可用的数据类型列表

        Returns:
            数据类型信息列表
        """
        return [
            {
                "type": "s5p_no2",
                "name": "Sentinel-5P NO2柱浓度",
                "parameter": "NO2",
                "resolution": "5.5km",
                "unit": "mol/m2",
                "applications": ["机动车排放", "工业污染", "交通排放"]
            },
            {
                "type": "modis_aod",
                "name": "MODIS气溶胶光学厚度",
                "parameter": "AOD",
                "resolution": "3km",
                "unit": "dimensionless",
                "applications": ["细颗粒物", "沙尘监测", "污染传输"]
            },
            {
                "type": "s5p_so2",
                "name": "Sentinel-5P SO2柱浓度",
                "parameter": "SO2",
                "resolution": "5.5km",
                "unit": "molec/cm2",
                "applications": ["火山活动", "工业排放", "燃煤污染"]
            },
            {
                "type": "s5p_co",
                "name": "Sentinel-5P CO柱浓度",
                "parameter": "CO",
                "resolution": "7km",
                "unit": "mol/m2",
                "applications": ["生物质燃烧", "交通排放", "不完全燃烧"]
            },
            {
                "type": "s5p_hcho",
                "name": "Sentinel-5P HCHO柱浓度",
                "parameter": "HCHO",
                "resolution": "5.5km",
                "unit": "mol/m2",
                "applications": ["VOCs排放", "光化学污染", "生物排放"]
            },
            {
                "type": "s5p_o3",
                "name": "Sentinel-5P O3柱浓度",
                "parameter": "O3",
                "resolution": "5.5km",
                "unit": "mol/m2",
                "applications": ["臭氧污染", "光化学烟雾", "区域传输"]
            },
            {
                "type": "s5p_aer_ai",
                "name": "Sentinel-5P气溶胶指数",
                "parameter": "Aerosol Index",
                "resolution": "5.5km",
                "unit": "dimensionless",
                "applications": ["沙尘监测", "烟雾检测", "污染层识别"]
            }
        ]