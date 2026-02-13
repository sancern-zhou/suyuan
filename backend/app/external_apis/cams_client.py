"""
CAMS API Client

Copernicus Atmosphere Monitoring Service (CAMS)
提供全球气溶胶预报数据，包括沙尘气溶胶
"""
from typing import Dict, Any, Optional, List
import httpx
from datetime import datetime, timedelta
import structlog
import os
import tempfile
import json

logger = structlog.get_logger()


class CAMSClient:
    """
    CAMS API客户端

    提供CAMS气溶胶预报数据查询功能：
    - 沙尘气溶胶光学厚度 (Dust AOD)
    - PM10浓度预报
    - 地面浓度
    - 柱浓度

    数据来源: https://atmosphere.copernicus.eu/
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        """
        初始化CAMS客户端

        Args:
            api_key: CAMS ADS API Key (从环境变量或参数获取)
            api_url: CAMS API URL (可选，默认使用ADS API)

        Note:
            API Key需要从 https://ads.atmosphere.copernicus.eu/ 注册获取
            注册后在 ~/.cdsapirc 或环境变量中配置
        """
        self.api_key = api_key or os.getenv("CAMS_API_KEY")
        self.api_url = api_url or os.getenv(
            "CAMS_API_URL",
            "https://ads.atmosphere.copernicus.eu/api/v2"
        )
        self.timeout = 300  # CAMS数据处理可能需要较长时间（5分钟）

        # 检查是否有cdsapi库
        self.has_cdsapi = self._check_cdsapi()

    def _check_cdsapi(self) -> bool:
        """检查是否安装了cdsapi库"""
        try:
            import cdsapi
            return True
        except ImportError:
            logger.warning(
                "cdsapi_not_installed",
                message="cdsapi库未安装，将使用REST API备用方案。推荐安装: pip install cdsapi"
            )
            return False

    async def fetch_dust_forecast(
        self,
        min_lat: float = 15.0,
        max_lat: float = 55.0,
        min_lon: float = 70.0,
        max_lon: float = 140.0,
        forecast_hours: int = 120,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取沙尘预报数据

        Args:
            min_lat: 最小纬度（中国区域默认15°N）
            max_lat: 最大纬度（中国区域默认55°N）
            min_lon: 最小经度（中国区域默认70°E）
            max_lon: 最大经度（中国区域默认140°E）
            forecast_hours: 预报时长（小时，默认120小时=5天）
            date: 预报基准日期（YYYY-MM-DD格式，默认今天）

        Returns:
            Dict: 沙尘预报数据，包含：
                - dust_aod_550nm: 沙尘气溶胶光学厚度
                - particulate_matter_10um: PM10浓度预报
                - metadata: 预报元数据

        Raises:
            Exception: API调用失败
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logger.info(
            "cams_fetch_start",
            bbox=[min_lat, max_lat, min_lon, max_lon],
            forecast_hours=forecast_hours,
            date=date
        )

        # 如果有cdsapi库，使用官方客户端
        if self.has_cdsapi:
            return await self._fetch_with_cdsapi(
                min_lat, max_lat, min_lon, max_lon,
                forecast_hours, date
            )
        else:
            # 否则使用REST API备用方案
            return await self._fetch_with_rest_api(
                min_lat, max_lat, min_lon, max_lon,
                forecast_hours, date
            )

    async def _fetch_with_cdsapi(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        forecast_hours: int,
        date: str
    ) -> Dict[str, Any]:
        """
        使用cdsapi库获取数据（推荐方式）

        Note: 这个方法需要在异步上下文中运行阻塞的cdsapi调用
        """
        import cdsapi
        import asyncio
        from functools import partial

        try:
            # 创建CAMS客户端
            c = cdsapi.Client(
                url=self.api_url,
                key=self.api_key,
                verify=True
            )

            # 生成leadtime_hour列表 (0, 3, 6, ..., forecast_hours)
            leadtime_hours = [str(h) for h in range(0, forecast_hours + 1, 3)]

            # 请求参数
            request = {
                'variable': [
                    'dust_aerosol_optical_depth_550nm',
                    'particulate_matter_10um'
                ],
                'date': date,
                'time': '00:00',
                'leadtime_hour': leadtime_hours,
                'area': [max_lat, min_lon, min_lat, max_lon],  # N, W, S, E
                'format': 'netcdf'
            }

            # 临时文件保存下载的NetCDF
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.nc',
                delete=False
            )
            temp_file.close()

            logger.info(
                "cams_requesting",
                dataset="cams-global-atmospheric-composition-forecasts",
                request=request,
                output_file=temp_file.name
            )

            # 在线程池中执行阻塞的retrieve调用
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                partial(
                    c.retrieve,
                    'cams-global-atmospheric-composition-forecasts',
                    request,
                    temp_file.name
                )
            )

            logger.info("cams_download_complete", file=temp_file.name)

            # 解析NetCDF文件
            result = await self._parse_netcdf(temp_file.name)

            # 清理临时文件
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error("cams_cdsapi_failed", error=str(e), exc_info=True)
            raise Exception(f"CAMS cdsapi request failed: {e}")

    async def _fetch_with_rest_api(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        forecast_hours: int,
        date: str
    ) -> Dict[str, Any]:
        """
        使用REST API获取数据（备用方案）

        Note: 这是一个简化的实现，实际CAMS REST API需要认证流程
        """
        logger.warning(
            "cams_using_rest_api",
            message="使用REST API备用方案，功能可能受限。建议安装cdsapi: pip install cdsapi"
        )

        # REST API实现（简化版）
        # 实际需要完整的OAuth2认证流程
        raise NotImplementedError(
            "CAMS REST API备用方案尚未实现。请安装cdsapi库: pip install cdsapi"
        )

    async def _parse_netcdf(self, netcdf_file: str) -> Dict[str, Any]:
        """
        解析NetCDF格式的CAMS数据

        Args:
            netcdf_file: NetCDF文件路径

        Returns:
            Dict: 解析后的数据
        """
        try:
            import xarray as xr
            import numpy as np

            # 打开NetCDF文件
            ds = xr.open_dataset(netcdf_file)

            logger.info(
                "netcdf_opened",
                variables=list(ds.data_vars.keys()),
                coords=list(ds.coords.keys())
            )

            # 提取数据
            result = {
                "success": True,
                "forecast_date": str(ds.attrs.get('date', '')),
                "variables": {},
                "coordinates": {
                    "latitude": ds.coords['latitude'].values.tolist(),
                    "longitude": ds.coords['longitude'].values.tolist(),
                    "time": [str(t) for t in ds.coords['time'].values]
                },
                "metadata": dict(ds.attrs)
            }

            # 提取变量数据
            for var_name in ds.data_vars:
                var = ds[var_name]

                # 转换为普通Python类型（处理NaN）
                data = var.values
                data = np.where(np.isnan(data), None, data)

                result["variables"][var_name] = {
                    "data": data.tolist(),
                    "units": var.attrs.get('units', ''),
                    "long_name": var.attrs.get('long_name', ''),
                    "shape": list(data.shape)
                }

            ds.close()

            logger.info(
                "netcdf_parsed",
                variables=list(result["variables"].keys())
            )

            return result

        except ImportError:
            logger.error(
                "xarray_not_installed",
                message="xarray库未安装，无法解析NetCDF。请安装: pip install xarray netCDF4"
            )
            raise Exception("xarray库未安装")
        except Exception as e:
            logger.error("netcdf_parse_failed", error=str(e), exc_info=True)
            raise

    def check_dependencies(self) -> Dict[str, bool]:
        """
        检查依赖库安装状态

        Returns:
            Dict: 依赖库状态
        """
        dependencies = {}

        # 检查cdsapi
        try:
            import cdsapi
            dependencies['cdsapi'] = True
        except ImportError:
            dependencies['cdsapi'] = False

        # 检查xarray
        try:
            import xarray
            dependencies['xarray'] = True
        except ImportError:
            dependencies['xarray'] = False

        # 检查netCDF4
        try:
            import netCDF4
            dependencies['netCDF4'] = True
        except ImportError:
            dependencies['netCDF4'] = False

        return dependencies

    def get_installation_instructions(self) -> str:
        """
        获取依赖库安装说明

        Returns:
            str: 安装说明
        """
        deps = self.check_dependencies()
        missing = [name for name, installed in deps.items() if not installed]

        if not missing:
            return "所有依赖库已安装 ✅"

        instructions = [
            "缺少以下依赖库：",
            ""
        ]

        for lib in missing:
            instructions.append(f"- {lib}")

        instructions.extend([
            "",
            "安装命令：",
            "pip install cdsapi xarray netCDF4",
            "",
            "CAMS API配置：",
            "1. 注册账号: https://ads.atmosphere.copernicus.eu/",
            "2. 获取API Key",
            "3. 配置 ~/.cdsapirc 或设置环境变量 CAMS_API_KEY"
        ])

        return "\n".join(instructions)


# 导出
__all__ = ["CAMSClient"]
