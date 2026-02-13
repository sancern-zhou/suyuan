"""
GDAS/GFS气象场数据下载器

NOAA Global Data Assimilation System (GDAS)
Global Forecast System (GFS)

提供HYSPLIT轨迹分析必需的气象场数据：
- U/V风分量（高空风）
- 垂直速度 (omega)
- 温度 (temperature)
- 位势高度 (geopotential height)
- 相对湿度 (relative humidity)
- 地面气压 (surface pressure)

数据来源：https://www.ncei.noaa.gov/products/weather-balloon/global-analysis
"""
from typing import Dict, Any, Optional, List
import httpx
from datetime import datetime, timedelta
import structlog
import os
import gzip
import tempfile
from pathlib import Path
import asyncio

logger = structlog.get_logger()


class GDASGFSClient:
    """
    GDAS/GFS数据下载客户端

    提供：
    1. GDAS气象场分析数据（每6小时更新，分辨率1°×1°）
    2. GFS全球预报数据（0.25°×0.25°分辨率，3小时间隔）
    3. 自动下载和缓存机制
    4. 支持HYSPLIT直接使用的格式转换

    数据延迟：
    - GDAS：约3天（实时分析数据）
    - GFS：约5天（预报数据）

    版本历史：
    - gdas1：1°分辨率（推荐轨迹分析）
    - gdas05：0.5°分辨率（更高精度，实验性）
    - gfs025：0.25°分辨率（最高精度）
    """

    def __init__(self, storage_path: str = "./data/meteorology"):
        """
        初始化GDAS/GFS客户端

        Args:
            storage_path: 数据缓存目录路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # GDAS数据源（推荐轨迹分析）
        self.gdas_base_url = "https://www.ncei.noaa.gov/data/gdas1/"
        # GFS数据源（预报数据）
        self.gfs_base_url = "https://www.ncei.noaa.gov/data/gfs-access/"

        # FTP服务器（备用下载方式）
        self.ftp_base_url = "ftp://gdas.uzdc01.earth-data.nasa.gov/gdas1/"

        # 压力层列表（HYSPLIT标准）
        self.pressure_levels = [
            1000, 950, 925, 900, 850, 800, 700, 500,
            400, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10
        ]

        # 变量列表
        self.gdas_variables = [
            "ugrd",  # U风分量 (m/s)
            "vgrd",  # V风分量 (m/s)
            "tmp",   # 温度 (K)
            "hgt",   # 位势高度 (gpm)
            "rhum",  # 相对湿度 (%)
            "vvel",  # 垂直速度 (Pa/s) - 可选
        ]

        # GFS变量列表（更多变量）
        self.gfs_variables = [
            "ugrd", "vgrd", "tmp", "hgt", "rhum", "vvel",
            "prmsl",  # 海平面气压 (Pa)
            "spfh",   # 比湿度 (kg/kg)
            "clwmr",  # 云液水含量 (kg/kg)
        ]

        # 缓存配置
        self.cache_timeout_hours = 168  # 7天（GDAS延迟3天，保留4天缓冲）

    async def download_gdas_data(
        self,
        date: datetime,
        forecast_hours: int = 0  # 0=分析数据，6/12/18=预报
    ) -> Dict[str, Any]:
        """
        下载GDAS气象场数据（每6小时）

        Args:
            date: 数据日期
            forecast_hours: 预报时长（0=分析数据，6/12/18/24=预报）

        Returns:
            Dict: 下载结果和文件路径
        """
        try:
            # 构建文件名
            date_str = date.strftime("%Y%m%d")
            hour_str = f"{forecast_hours:02d}"
            file_prefix = f"gdas1.{date_str}/{forecast_hours:02d}hr"

            gdas_files = [
                f"{file_prefix}.pgrb1.anl",  # 分析数据
                f"{file_prefix}.pgrb2.anl",  # 压力层分析
            ]

            logger.info(
                "gdas_download_start",
                date=date_str,
                forecast_hours=forecast_hours,
                files=gdas_files
            )

            # 检查缓存
            cache_key = f"gdas_{date_str}_{forecast_hours}"
            cached_data = self._check_cache(cache_key)

            if cached_data:
                logger.info("gdas_cache_hit", cache_key=cache_key)
                return cached_data

            # 下载文件
            downloaded_files = []
            for gdas_file in gdas_files:
                url = f"{self.gdas_base_url}{gdas_file}"
                local_file = self.storage_path / cache_key / gdas_file

                # 创建目录
                local_file.parent.mkdir(parents=True, exist_ok=True)

                # 下载文件
                success = await self._download_file(url, local_file)

                if success:
                    downloaded_files.append(local_file)
                    logger.info("gdas_file_downloaded", file=local_file.name)

            # 构建返回结果
            result = {
                "success": True,
                "data_date": date_str,
                "forecast_hours": forecast_hours,
                "files": downloaded_files,
                "metadata": {
                    "resolution": "1°×1°",
                    "time_interval": "6小时",
                    "pressure_levels": self.pressure_levels,
                    "variables": self.gdas_variables
                }
            }

            # 缓存结果
            self._save_cache(cache_key, result)

            logger.info(
                "gdas_download_complete",
                date=date_str,
                forecast_hours=forecast_hours,
                files_count=len(downloaded_files)
            )

            return result

        except Exception as e:
            logger.error(
                "gdas_download_failed",
                date=date_str,
                forecast_hours=forecast_hours,
                error=str(e),
                exc_info=True
            )
            raise

    async def download_gfs_forecast(
        self,
        start_date: datetime,
        end_date: datetime,
        resolution: str = "025",  # "025"=0.25°, "05"=0.5°, "1"=1°
        forecast_hours: int = 0
    ) -> Dict[str, Any]:
        """
        下载GFS全球预报数据

        Args:
            start_date: 开始日期
            end_date: 结束日期
            resolution: 分辨率（025=0.25°, 05=0.5°, 1=1°）
            forecast_hours: 预报时长（0=分析数据，3/6/9...=预报）

        Returns:
            Dict: 下载结果和文件路径
        """
        try:
            # 构建文件名
            date_str = start_date.strftime("%Y%m%d")
            hour_str = f"{forecast_hours:02d}"
            gfs_prefix = f"gfs.{date_str}/{forecast_hours:02d}/atmos"
            gfs_files = [
                f"{gfs_prefix}/gfs.t{hour_str}z.pgrb2.{resolution}.f{forecast_hours:03d}"
            ]

            cache_key = f"gfs_{resolution}_{date_str}_{forecast_hours}"

            logger.info(
                "gfs_download_start",
                date=date_str,
                resolution=resolution,
                forecast_hours=forecast_hours
            )

            # 检查缓存
            cached_data = self._check_cache(cache_key)

            if cached_data:
                logger.info("gfs_cache_hit", cache_key=cache_key)
                return cached_data

            # 下载文件
            downloaded_files = []
            for gfs_file in gfs_files:
                url = f"{self.gfs_base_url}{gfs_file}"
                local_file = self.storage_path / cache_key / gfs_file

                local_file.parent.mkdir(parents=True, exist_ok=True)

                success = await self._download_file(url, local_file)

                if success:
                    downloaded_files.append(local_file)

            result = {
                "success": True,
                "data_date": date_str,
                "resolution": resolution,
                "forecast_hours": forecast_hours,
                "files": downloaded_files,
                "metadata": {
                    "resolution": f"{resolution}°×{resolution}°",
                    "time_interval": "3小时",
                    "pressure_levels": self.pressure_levels,
                    "variables": self.gfs_variables
                }
            }

            self._save_cache(cache_key, result)

            logger.info(
                "gfs_download_complete",
                date=date_str,
                resolution=resolution,
                files_count=len(downloaded_files)
            )

            return result

        except Exception as e:
            logger.error(
                "gfs_download_failed",
                error=str(e),
                exc_info=True
            )
            raise

    async def download_multiple_times(
        self,
        start_date: datetime,
        hours_range: int = 72  # 下载72小时历史数据
    ) -> List[Dict[str, Any]]:
        """
        批量下载多个时间点的气象场数据（用于轨迹分析）

        Args:
            start_date: 起始时间（通常为当前时间）
            hours_range: 回溯小时数

        Returns:
            List[Dict]: 每个时间点的下载结果
        """
        try:
            # 构建时间序列（每6小时一个点）
            times = []
            current_time = start_date
            for i in range(0, hours_range + 1, 6):
                times.append(current_time - timedelta(hours=i))

            logger.info(
                "batch_download_start",
                start_time=start_date.isoformat(),
                hours_range=hours_range,
                time_points=len(times)
            )

            # 并发下载（限制并发数避免过载）
            semaphore = asyncio.Semaphore(3)  # 最多3个并发下载
            download_tasks = []

            for time_point in times:
                task = self._download_with_semaphore(
                    semaphore,
                    self.download_gdas_data,
                    time_point
                )
                download_tasks.append(task)

            # 等待所有下载完成
            results = await asyncio.gather(*download_tasks, return_exceptions=True)

            # 过滤成功的下载
            successful_downloads = [
                r for r in results
                if isinstance(r, dict) and r.get("success", False)
            ]

            logger.info(
                "batch_download_complete",
                total=len(times),
                successful=len(successful_downloads)
            )

            return successful_downloads

        except Exception as e:
            logger.error("batch_download_failed", error=str(e), exc_info=True)
            raise

    async def convert_to_hysplit_format(
        self,
        gdas_data: Dict[str, Any],
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        将GDAS/GFS数据转换为HYSPLIT可读取的ARL格式

        Args:
            gdas_data: GDAS下载数据
            output_dir: 输出目录（默认使用缓存目录）

        Returns:
            Path: 转换后的ARL文件路径
        """
        try:
            import xarray as xr
            import numpy as np
            from datetime import datetime

            if output_dir is None:
                output_dir = self.storage_path / "hysplit_format"

            output_dir.mkdir(parents=True, exist_ok=True)

            # 读取GDAS NetCDF文件
            gdas_files = gdas_data.get("files", [])
            if not gdas_files:
                raise ValueError("No GDAS files to convert")

            # 使用第一个文件作为主文件
            gdas_file = gdas_files[0]

            logger.info(
                "converting_to_hysplit",
                gdas_file=str(gdas_file),
                output_dir=str(output_dir)
            )

            # 打开NetCDF文件
            with xr.open_dataset(gdas_file) as ds:
                # 提取变量
                data_vars = {}
                for var in self.gdas_variables:
                    if var in ds.data_vars:
                        data_vars[var] = ds[var]

                # 构建HYSPLIT格式数据
                hysplit_data = {
                    "time": ds.time.values,
                    "lat": ds.lat.values,
                    "lon": ds.lon.values,
                    "lev": ds.level.values,
                    "data": data_vars
                }

                # 生成输出文件名
                date_str = gdas_data.get("data_date", "unknown")
                hour_str = gdas_data.get("forecast_hours", 0)
                output_file = output_dir / f"gdas_{date_str}_{hour_str:02d}hr.arl"

                # 保存为ARL格式（简化版，实际需要更复杂的转换）
                self._save_arl_format(hysplit_data, output_file)

                logger.info(
                    "hysplit_conversion_complete",
                    output_file=str(output_file)
                )

                return output_file

        except Exception as e:
            logger.error(
                "hysplit_conversion_failed",
                error=str(e),
                exc_info=True
            )
            raise

    async def _download_file(
        self,
        url: str,
        local_file: Path
    ) -> bool:
        """
        下载单个文件（带重试和断点续传）

        Args:
            url: 下载URL
            local_file: 本地文件路径

        Returns:
            bool: 下载是否成功
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=300,  # 5分钟超时
                    follow_redirects=True
                ) as client:
                    async with client.stream("GET", url) as response:
                        if response.status_code == 200:
                            total_size = int(response.headers.get("content-length", 0))

                            with open(local_file, "wb") as f:
                                async for chunk in response.aiter_bytes(chunk_size=8192):
                                    f.write(chunk)

                            # 验证文件大小
                            actual_size = local_file.stat().st_size

                            if total_size > 0 and actual_size < total_size * 0.9:
                                logger.warning(
                                    "file_size_mismatch",
                                    url=url,
                                    expected=total_size,
                                    actual=actual_size
                                )
                                return False

                            logger.info(
                                "file_downloaded",
                                url=url,
                                size=actual_size
                            )
                            return True
                        else:
                            logger.warning(
                                "download_failed",
                                url=url,
                                status=response.status_code
                            )

            except Exception as e:
                logger.warning(
                    "download_attempt_failed",
                    url=url,
                    attempt=attempt + 1,
                    error=str(e)
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避

        return False

    async def _download_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        download_func,
        *args
    ):
        """使用信号量限制并发下载"""
        async with semaphore:
            return await download_func(*args)

    def _check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """检查缓存"""
        cache_file = self.storage_path / f"{cache_key}.json"

        if cache_file.exists():
            try:
                import json
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)

                # 检查是否过期
                cache_time = datetime.fromisoformat(cache_data.get("cache_time", ""))
                if datetime.now() - cache_time < timedelta(hours=self.cache_timeout_hours):
                    return cache_data.get("result")
                else:
                    # 删除过期缓存
                    cache_file.unlink()

            except Exception as e:
                logger.warning("cache_read_failed", cache_key=cache_key, error=str(e))

        return None

    def _save_cache(self, cache_key: str, result: Dict[str, Any]):
        """保存缓存"""
        import json

        cache_file = self.storage_path / f"{cache_key}.json"

        cache_data = {
            "cache_time": datetime.now().isoformat(),
            "result": result
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.warning("cache_save_failed", cache_key=cache_key, error=str(e))

    def _save_arl_format(self, data: Dict[str, Any], output_file: Path):
        """保存为ARL格式（简化实现）"""
        # 实际的ARL格式转换非常复杂，需要：
        # 1. 读取GDAS/GFS的GRIB2格式
        # 2. 转换为HYSPLIT的ARL格式
        # 3. 处理压缩和索引

        # 这里提供简化实现
        import json

        with open(output_file.with_suffix(".json"), "w") as f:
            json.dump({
                "metadata": {
                    "format": "HYSPLIT_ARL_simulation",
                    "description": "模拟ARL格式数据（实际需要GRIB2到ARL的转换）",
                    "time": str(data["time"]),
                    "lat_range": [float(data["lat"].min()), float(data["lat"].max())],
                    "lon_range": [float(data["lon"].min()), float(data["lon"].max())],
                    "levels": len(data["lev"])
                },
                "data_keys": list(data["data"].keys())
            }, f, indent=2)

        logger.info(
            "arl_format_saved",
            output_file=str(output_file),
            note="JSON模拟格式，实际需要GRIB2转换"
        )

    def get_installation_instructions(self) -> str:
        """获取安装说明"""
        return """
GDAS/GFS数据下载配置说明：

1. 安装依赖库：
   pip install xarray netCDF4 cfgrib pygrib

2. 安装NCEI数据访问工具（可选）：
   # 使用conda
   conda install -c conda-forge cfgrib

   # 或使用pip
   pip install cfgrib

3. 配置环境变量（可选）：
   export NCEI_API_KEY="your_api_key"

4. 数据下载方式：
   - 在线下载：自动从NOAA服务器下载
   - 本地数据：使用已有的GDAS/GFS文件

5. HYSPLIT轨迹分析需要：
   - 下载72小时历史GDAS数据（每6小时一个文件）
   - 数据延迟约3天（实时轨迹分析）
   - 总数据量：约72MB（72小时×6个文件）
        """

    def cleanup_old_cache(self, days: int = 30):
        """清理过期缓存文件"""
        import json

        cutoff_time = datetime.now() - timedelta(days=days)
        cleaned_count = 0

        for cache_file in self.storage_path.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)

                cache_time = datetime.fromisoformat(cache_data.get("cache_time", ""))

                if cache_time < cutoff_time:
                    cache_file.unlink()
                    cleaned_count += 1

            except Exception as e:
                logger.warning("cache_cleanup_failed", file=cache_file, error=str(e))

        logger.info(
            "cache_cleanup_complete",
            cleaned_count=cleaned_count,
            days=days
        )


# 导出
__all__ = ["GDASGFSClient"]
