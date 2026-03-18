"""
GFS数据预处理工具

将下载的GFS GRIB2文件转换为NetCDF格式，并提取关键变量
- 支持批量加载多个GFS时次
- 提取U/V风速、垂直速度、位势高度、地形
- 合并为统一数据集
- 输出NetCDF格式供轨迹模拟使用

依赖:
- xarray, cfgrib, netCDF4, eccodes
"""

from typing import Dict, List, Any, Optional, Tuple
import os
import glob
import asyncio
from pathlib import Path
import pandas as pd
import numpy as np
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

try:
    import xarray as xr
    HAS_XARRAY = True
except ImportError:
    HAS_XARRAY = False

try:
    import cfgrib
    HAS_CFGRID = True
except ImportError:
    HAS_CFGRID = False


class GFSProcessorTool(LLMTool):
    """GFS数据预处理工具"""

    def __init__(self):
        function_schema = {
            "name": "process_gfs_data",
            "description": """
预处理GFS气象数据

将GFS GRIB2文件转换为NetCDF格式，并提取关键变量

**输入**:
- gfs_files_pattern: GFS文件路径模式（默认 data/gfs/*.f*）
- extract_variables: 要提取的变量列表（默认 ['u', 'v', 'wz', 'gh', 'orog']）

**输出**:
- gfs_combined.nc: 合并后的GFS数据集
- orog.nc: 地形数据（单独存储）
- 统计信息和处理日志

**变量说明**:
- u: U风分量 (m/s)
- v: V风分量 (m/s)
- wz: 垂直速度 (Pa/s)
- gh: 位势高度 (m)
- orog: 地形高度 (m)
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "gfs_files_pattern": {
                        "type": "string",
                        "description": "GFS文件路径模式（默认 data/gfs/*.f*）",
                        "default": "data/gfs/*.f*"
                    },
                    "extract_variables": {
                        "type": "array",
                        "description": "要提取的变量列表",
                        "items": {"type": "string"},
                        "default": ["u", "v", "wz", "gh", "orog"]
                    },
                    "output_combined": {
                        "type": "boolean",
                        "description": "是否合并所有时次为一个文件（默认True）",
                        "default": True
                    }
                },
                "required": ["gfs_files_pattern"]
            }
        }

        super().__init__(
            name="process_gfs_data",
            description="Process GFS meteorological data",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        # 变量映射（GRIB2变量名 -> 标准变量名）
        self.variable_mapping = {
            'u_component_of_wind': 'u',
            'v_component_of_wind': 'v',
            'vertical_velocity': 'wz',
            'geopotential_height': 'gh',
            'orography': 'orog'
        }

        # 输出目录
        self.output_dir = Path("data/gfs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute(
        self,
        gfs_files_pattern: str = "data/gfs/*.f*",
        extract_variables: List[str] = None,
        output_combined: bool = True
    ) -> Dict[str, Any]:
        """
        预处理GFS数据

        Args:
            gfs_files_pattern: GFS文件路径模式
            extract_variables: 要提取的变量列表
            output_combined: 是否合并输出

        Returns:
            处理结果统计
        """
        # 验证依赖
        if not HAS_XARRAY or not HAS_CFGRID:
            raise ImportError(
                "需要安装 xarray 和 cfgrib 库: pip install xarray cfgrib netCDF4 eccodes"
            )

        # 默认变量
        if extract_variables is None:
            extract_variables = ['u', 'v', 'wz', 'gh', 'orog']

        # 查找GFS文件
        file_list = sorted(glob.glob(gfs_files_pattern))
        if not file_list:
            raise FileNotFoundError(f"未找到GFS文件: {gfs_files_pattern}")

        logger.info(
            "gfs_processing_start",
            file_count=len(file_list),
            variables=extract_variables,
            pattern=gfs_files_pattern
        )

        # 预加载GFS数据
        gfs_datasets = []
        orog_data = None

        # 并发加载文件
        tasks = [self._load_gfs_file(file_path) for file_path in file_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理加载结果
        for i, result in enumerate(results):
            file_path = file_list[i]
            if isinstance(result, Exception):
                logger.error(
                    "gfs_file_load_failed",
                    file=file_path,
                    error=str(result)
                )
            elif result is not None:
                gfs_datasets.append(result)

        if not gfs_datasets:
            raise RuntimeError("未能加载任何GFS文件")

        # 提取地形数据（从第一个文件）
        logger.info("Extracting orography data")
        orog_data = gfs_datasets[0][['orog']] if 'orog' in gfs_datasets[0] else None

        # 合并数据
        if output_combined and len(gfs_datasets) > 1:
            logger.info("Merging GFS datasets")
            try:
                combined_ds = xr.concat(
                    gfs_datasets,
                    dim='time',
                    data_vars='minimal'
                )
                output_file = self.output_dir / "gfs_combined.nc"
                combined_ds.to_netcdf(output_file)
                logger.info("gfs_combined_file_saved", file=str(output_file))
            except Exception as e:
                logger.error("gfs_merge_failed", error=str(e))
                # 失败时保存第一个文件
                output_file = self.output_dir / f"gfs_{Path(file_list[0]).stem}.nc"
                gfs_datasets[0].to_netcdf(output_file)
                logger.info("gfs_single_file_saved", file=str(output_file))
        else:
            # 保存第一个文件
            output_file = self.output_dir / f"gfs_{Path(file_list[0]).stem}.nc"
            gfs_datasets[0].to_netcdf(output_file)
            logger.info("gfs_single_file_saved", file=str(output_file))

        # 保存地形数据（单独）
        orog_file = self.output_dir / "orog.nc"
        if orog_data is not None:
            orog_data.to_netcdf(orog_file)
            logger.info("orog_file_saved", file=str(orog_file))

        # 生成统计信息
        stats = {
            "files_processed": len(file_list),
            "files_loaded": len(gfs_datasets),
            "output_file": str(output_file),
            "orog_file": str(orog_file) if orog_data is not None else None,
            "variables": extract_variables,
            "time_range": {
                "start": str(gfs_datasets[0].time.values) if gfs_datasets else None,
                "end": str(gfs_datasets[-1].time.values) if gfs_datasets else None
            },
            "spatial_extent": {
                "lon_min": float(gfs_datasets[0].longitude.min()) if gfs_datasets else None,
                "lon_max": float(gfs_datasets[0].longitude.max()) if gfs_datasets else None,
                "lat_min": float(gfs_datasets[0].latitude.min()) if gfs_datasets else None,
                "lat_max": float(gfs_datasets[0].latitude.max()) if gfs_datasets else None
            }
        }

        logger.info(
            "gfs_processing_complete",
            files_loaded=len(gfs_datasets),
            output_file=str(output_file)
        )

        return {
            "status": "success",
            "success": True,
            "data": stats,
            "metadata": {
                "processing_time": pd.Timestamp.now().isoformat(),
                "tool_version": "1.0.0",
                "schema_version": "v2.0"
            },
            "summary": f"✅ GFS数据预处理完成: 加载 {len(gfs_datasets)}/{len(file_list)} 个文件，输出 {output_file.name}"
        }

    async def _load_gfs_file(self, file_path: str):
        """加载单个GFS文件

        Returns:
            Optional[xr.Dataset]: 加载的数据集，如果失败则返回None
        """
        try:
            # 使用cfgrib引擎打开GRIB2文件
            # 打开等压面数据
            ds_isobaric = xr.open_dataset(
                file_path,
                engine='cfgrib',
                backend_kwargs={
                    'indexpath': '',
                    'filter_by_keys': {
                        'typeOfLevel': 'isobaricInhPa'
                    }
                }
            )

            # 打开地表数据
            try:
                ds_surface = xr.open_dataset(
                    file_path,
                    engine='cfgrib',
                    backend_kwargs={
                        'indexpath': '',
                        'filter_by_keys': {
                            'typeOfLevel': 'surface'
                        }
                    }
                )
            except Exception as e:
                logger.debug(
                    "gfs_surface_load_failed",
                    file=file_path,
                    error=str(e)
                )
                ds_surface = None

            # 合并数据集
            if ds_surface is not None:
                ds_combined = ds_isobaric.merge(ds_surface, compat='override')
            else:
                ds_combined = ds_isobaric

            # 重命名变量
            for old_name, new_name in self.variable_mapping.items():
                if old_name in ds_combined:
                    ds_combined = ds_combined.rename({old_name: new_name})

            # 清理坐标
            ds_combined = ds_combined.drop_vars([
                'time_bound', 'valid_time', 'step'
            ], errors='ignore')

            return ds_combined

        except Exception as e:
            logger.error(
                "gfs_file_load_error",
                file=file_path,
                error=str(e)
            )
            return None


# 便利函数：检查GFS数据完整性
def validate_gfs_data(gfs_file: str) -> Dict[str, Any]:
    """
    验证GFS数据文件完整性

    Args:
        gfs_file: GFS NetCDF文件路径

    Returns:
        验证结果
    """
    if not HAS_XARRAY:
        return {"valid": False, "error": "xarray not installed"}

    try:
        ds = xr.open_dataset(gfs_file)

        # 检查必要变量
        required_vars = ['u', 'v', 'gh']
        missing_vars = [var for var in required_vars if var not in ds]

        if missing_vars:
            return {
                "valid": False,
                "missing_variables": missing_vars
            }

        # 检查维度
        dims = ds.dims
        required_dims = ['time', 'latitude', 'longitude']

        missing_dims = [dim for dim in required_dims if dim not in dims]

        if missing_dims:
            return {
                "valid": False,
                "missing_dimensions": missing_dims
            }

        # 返回数据统计
        return {
            "valid": True,
            "variables": list(ds.data_vars),
            "dimensions": dict(dims),
            "time_range": {
                "start": str(ds.time.values[0]),
                "end": str(ds.time.values[-1])
            } if 'time' in ds else None,
            "spatial_extent": {
                "longitude": [float(ds.longitude.min()), float(ds.longitude.max())],
                "latitude": [float(ds.latitude.min()), float(ds.latitude.max())]
            } if 'longitude' in ds and 'latitude' in ds else None,
            "file_size_mb": os.path.getsize(gfs_file) / (1024 * 1024)
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
