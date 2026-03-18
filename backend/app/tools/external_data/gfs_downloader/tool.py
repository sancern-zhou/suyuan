"""
GFS全球预报数据下载工具

从NOAA GFS全球预报系统下载气象数据
- 支持0.25°和0.5°分辨率
- 支持全球或区域裁剪（默认华南地区）
- 支持0-384小时预报时效
- 每6小时更新一次（00Z, 06Z, 12Z, 18Z）

依赖：
- xarray, cfgrib, netCDF4, eccodes
"""

from typing import Dict, List, Any, Optional
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import pandas as pd
import structlog
from pathlib import Path

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

try:
    import xarray as xr
    HAS_XARRAY = True
except ImportError:
    HAS_XARRAY = False


class GFSDownloaderTool(LLMTool):
    """GFS全球预报数据下载工具"""

    def __init__(self):
        function_schema = {
            "name": "download_gfs_data",
            "description": """
下载NOAA GFS全球预报数据

**数据源**: NOAA GFS (https://nomads.ncep.noaa.gov/)
**变量**: U/V风速、垂直速度、位势高度、地形高度
**分辨率**: 0.25°×0.25° 或 0.5°×0.5°
**预报时效**: 0-384小时（16天）
**更新频率**: 每6小时（00Z, 06Z, 12Z, 18Z）

**输入参数**:
- forecast_hours: 预报时长（0-384小时，默认120小时）
- region: 区域范围（south_china华南海量150W-120E, global全球）
- resolution: 分辨率（0p25=0.25°，0p50=0.5°，默认0p25）

**输出**:
- 下载的GFS文件列表
- 数据覆盖范围和统计信息
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "forecast_hours": {
                        "type": "integer",
                        "description": "预报时长（小时，0-384，默认120）",
                        "default": 120,
                        "minimum": 0,
                        "maximum": 384
                    },
                    "region": {
                        "type": "string",
                        "description": "区域范围（south_china华南海量150W-120E, global全球，默认south_china）",
                        "enum": ["south_china", "global"],
                        "default": "south_china"
                    },
                    "resolution": {
                        "type": "string",
                        "description": "分辨率（0p25=0.25°, 0p50=0.5°, 默认0p25）",
                        "enum": ["0p25", "0p50"],
                        "default": "0p25"
                    }
                },
                "required": ["forecast_hours"]
            }
        }

        super().__init__(
            name="download_gfs_data",
            description="Download NOAA GFS global forecast data",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        # GFS数据源配置
        self.base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_{resolution}.pl"
        self.output_dir = Path("data/gfs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 区域配置
        self.region_configs = {
            "south_china": {
                "leftlon": 100,
                "rightlon": 120,
                "toplat": 30,
                "bottomlat": 15
            },
            "global": {}  # 全球数据（无裁剪）
        }

        # GFS变量配置
        self.variables = {
            'UGRD': 'u_component_of_wind',  # U风分量
            'VGRD': 'v_component_of_wind',  # V风分量
            'DZDT': 'vertical_velocity',     # 垂直速度
            'HGT': 'geopotential_height',    # 位势高度
            'OROG': 'orography'              # 地形高度
        }

        # 高度层配置（等压面）
        self.levels = [
            'surface',      # 地表
            '1000_mb', '925_mb', '850_mb', '700_mb',
            '500_mb', '400_mb', '300_mb', '250_mb',
            '200_mb', '150_mb', '100_mb'
        ]

    async def execute(
        self,
        forecast_hours: int = 120,
        region: str = "south_china",
        resolution: str = "0p25"
    ) -> Dict[str, Any]:
        """
        下载GFS数据

        Args:
            forecast_hours: 预报时长（小时）
            region: 区域范围
            resolution: 分辨率

        Returns:
            下载结果统计
        """
        # 参数验证
        if forecast_hours < 0 or forecast_hours > 384:
            raise ValueError("预报时长必须在0-384小时之间")

        if region not in self.region_configs:
            raise ValueError(f"不支持的区域: {region}")

        # 记录下载开始
        logger.info(
            "gfs_download_start",
            forecast_hours=forecast_hours,
            region=region,
            resolution=resolution
        )

        # 初始化下载器
        downloader = GFSDataDownloader(
            base_url=self.base_url.format(resolution=resolution),
            output_dir=self.output_dir
        )

        # 获取区域配置
        region_config = self.region_configs[region]

        # 批量下载
        downloaded_files = []
        failed_files = []
        total_size_mb = 0

        # 创建任务列表
        tasks = []
        for hour in range(0, forecast_hours + 1):
            task = self._download_single_file(
                downloader=downloader,
                hour=hour,
                region_config=region_config,
                resolution=resolution
            )
            tasks.append(task)

        # 并发下载（限制并发数）
        semaphore = asyncio.Semaphore(5)  # 最多5个并发下载
        tasks_with_semaphore = [self._bounded_download(task, semaphore) for task in tasks]

        # 执行下载
        results = await asyncio.gather(*tasks_with_semaphore, return_exceptions=True)

        # 统计结果
        for i, result in enumerate(results):
            hour = i
            if isinstance(result, Exception):
                logger.error(
                    "gfs_download_failed",
                    hour=hour,
                    error=str(result)
                )
                failed_files.append(f"gfs.f{hour:03d}")
            elif result is not None:
                downloaded_files.append(result)
                total_size_mb += result.get('size_mb', 0)

        # 计算下载统计
        download_success_rate = len(downloaded_files) / (forecast_hours + 1) * 100

        # 保存元数据
        metadata = {
            "download_time": datetime.now().isoformat(),
            "forecast_hours": forecast_hours,
            "region": region,
            "resolution": resolution,
            "file_count": len(downloaded_files),
            "failed_count": len(failed_files),
            "success_rate": download_success_rate,
            "total_size_mb": round(total_size_mb, 2),
            "variables": list(self.variables.keys()),
            "levels": self.levels,
            "region_config": region_config
        }

        # 写入元数据文件
        metadata_file = self.output_dir / f"metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import json
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            "gfs_download_complete",
            success_rate=download_success_rate,
            total_files=forecast_hours + 1,
            downloaded=len(downloaded_files),
            failed=len(failed_files),
            total_size_mb=total_size_mb
        )

        # 返回结果
        return {
            "status": "success" if len(downloaded_files) > 0 else "partial_success",
            "success": len(downloaded_files) > 0,
            "data": {
                "downloaded_files": downloaded_files,
                "failed_files": failed_files,
                "statistics": {
                    "total_files": forecast_hours + 1,
                    "downloaded_count": len(downloaded_files),
                    "failed_count": len(failed_files),
                    "success_rate": round(download_success_rate, 2),
                    "total_size_mb": round(total_size_mb, 2)
                }
            },
            "metadata": metadata,
            "summary": f"✅ GFS数据下载完成: {len(downloaded_files)}/{forecast_hours + 1}文件成功 ({download_success_rate:.1f}%), 总大小 {total_size_mb:.1f} MB"
        }

    async def _bounded_download(self, task, semaphore):
        """限制并发下载"""
        async with semaphore:
            return await task

    async def _download_single_file(
        self,
        downloader: 'GFSDataDownloader',
        hour: int,
        region_config: Dict,
        resolution: str
    ) -> Optional[Dict[str, Any]]:
        """下载单个GFS文件"""
        filename = f"gfs.f{hour:03d}"
        file_path = self.output_dir / filename

        # 检查文件是否已存在
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.debug("gfs_file_exists", filename=filename, size_mb=size_mb)
            return {
                "filename": filename,
                "size_mb": round(size_mb, 2),
                "status": "exists"
            }

        # 下载文件
        try:
            result = await downloader.download_file(
                hour=hour,
                variables=list(self.variables.keys()),
                levels=self.levels,
                region=region_config,
                resolution=resolution
            )

            if result and file_path.exists():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                logger.info("gfs_download_success", filename=filename, size_mb=size_mb)
                return {
                    "filename": filename,
                    "size_mb": round(size_mb, 2),
                    "status": "downloaded"
                }
            else:
                logger.error("gfs_download_failed", filename=filename)
                return None

        except Exception as e:
            logger.error(
                "gfs_download_error",
                filename=filename,
                error=str(e)
            )
            raise


class GFSDataDownloader:
    """GFS数据下载器"""

    def __init__(self, base_url: str, output_dir: Path):
        self.base_url = base_url
        self.output_dir = output_dir
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def download_file(
        self,
        hour: int,
        variables: List[str],
        levels: List[str],
        region: Dict,
        resolution: str
    ) -> bool:
        """下载单个GFS文件"""
        if not self.session:
            self.session = aiohttp.ClientSession()

        # 构建URL参数
        params = {
            'file': f'gfs.t00z.pgrb2.{resolution}.f{hour:03d}',
            'all_lev': 'on' if 'surface' in levels else 'off'
        }

        # 添加变量
        for var in variables:
            params[f'var_{var}'] = 'on'

        # 添加高度层
        for level in levels:
            if level != 'surface':
                params[f'lev_{level}'] = 'on'
            else:
                params['lev_surface'] = 'on'

        # 添加区域裁剪
        if region:
            params.update(region)

        try:
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    file_path = self.output_dir / f"gfs.f{hour:03d}"
                    content = await response.read()
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    return True
                else:
                    logger.warning(
                        "gfs_download_http_error",
                        hour=hour,
                        status=response.status
                    )
                    return False

        except Exception as e:
            logger.error(
                "gfs_download_exception",
                hour=hour,
                error=str(e)
            )
            return False
