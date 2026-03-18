"""
Meteorological Data Manager - Phase 3.1 Module 5

气象数据管理器
负责GDAS数据下载、缓存管理和数据可用性检查

GDAS数据说明：
- 来源: NOAA ARL (Air Resources Laboratory)
- FTP: ftp://arlftp.arlhq.noaa.gov/pub/archives/gdas1/
- 格式: ARL格式，1度分辨率
- 文件命名: gdas1.MONYY.w[1-5] (例如: gdas1.nov25.w1 = 2025年11月第1周)
- 时间覆盖: 每周一个文件
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import ftplib
import structlog
import calendar
import time

logger = structlog.get_logger()


class MeteoDataManager:
    """
    气象数据管理器 - Phase 3.1 Module 5

    功能：
    - 从NOAA FTP下载GDAS1数据
    - 本地缓存管理
    - 数据可用性检查
    - 根据时间范围自动选择文件
    - 自动清理过期数据
    """

    # NOAA ARL FTP配置
    FTP_HOST = "arlftp.arlhq.noaa.gov"
    FTP_DIR = "/pub/archives/gdas1"

    # 月份缩写映射
    MONTH_ABBR = {
        1: "jan", 2: "feb", 3: "mar", 4: "apr",
        5: "may", 6: "jun", 7: "jul", 8: "aug",
        9: "sep", 10: "oct", 11: "nov", 12: "dec"
    }

    def __init__(
        self,
        cache_dir: str = "data/hysplit/meteo",
        max_cache_days: int = 30,
        ftp_timeout: int = 60
    ):
        """
        初始化气象数据管理器

        Args:
            cache_dir: 本地缓存目录
            max_cache_days: 最大缓存天数（自动清理）
            ftp_timeout: FTP连接超时时间（秒）
        """
        self.cache_dir = Path(cache_dir)
        self.max_cache_days = max_cache_days
        self.ftp_timeout = ftp_timeout

        # 创建缓存目录
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "meteo_data_manager_initialized",
            cache_dir=str(self.cache_dir),
            max_cache_days=max_cache_days
        )

    def get_required_files_for_timerange(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[str]:
        """
        根据时间范围计算需要的GDAS文件列表

        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）

        Returns:
            文件名列表，例如: ["gdas1.nov25.w1", "gdas1.nov25.w2"]
        """
        required_files = set()

        # 遍历时间范围内的每一天
        current = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_time.replace(hour=23, minute=59, second=59)

        while current <= end:
            filename = self._get_filename_for_date(current)
            required_files.add(filename)
            current += timedelta(days=1)

        result = sorted(list(required_files))

        logger.debug(
            "required_files_calculated",
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            file_count=len(result),
            files=result
        )

        return result

    def _get_filename_for_date(self, dt: datetime) -> str:
        """
        根据日期生成GDAS文件名

        Args:
            dt: 日期时间

        Returns:
            文件名，例如: "gdas1.nov25.w1"
        """
        # 获取月份缩写
        month_abbr = self.MONTH_ABBR[dt.month]

        # 获取年份后两位
        year_short = str(dt.year)[-2:]

        # 计算是该月的第几周（1-5）
        week_of_month = self._get_week_of_month(dt)

        filename = f"gdas1.{month_abbr}{year_short}.w{week_of_month}"

        return filename

    def _get_week_of_month(self, dt: datetime) -> int:
        """
        计算日期是当月第几周（1-5）

        按照NOAA的划分规则：
        - 每7天一个文件
        - 1-7日 = w1, 8-14日 = w2, 15-21日 = w3, 22-28日 = w4, 29-31日 = w5
        """
        day = dt.day

        if day <= 7:
            return 1
        elif day <= 14:
            return 2
        elif day <= 21:
            return 3
        elif day <= 28:
            return 4
        else:
            return 5

    def check_local_availability(
        self,
        filenames: List[str]
    ) -> Dict[str, bool]:
        """
        检查本地是否已有所需文件

        Args:
            filenames: 文件名列表

        Returns:
            {filename: is_available} 字典
        """
        availability = {}

        for filename in filenames:
            file_path = self.cache_dir / filename
            availability[filename] = file_path.exists() and file_path.stat().st_size > 0

        available_count = sum(availability.values())

        logger.debug(
            "local_availability_checked",
            total_files=len(filenames),
            available=available_count,
            missing=len(filenames) - available_count
        )

        return availability

    def download_file(
        self,
        filename: str,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        从NOAA FTP下载单个GDAS文件

        Args:
            filename: 文件名，例如 "gdas1.nov25.w1"
            force_redownload: 强制重新下载（即使本地已有）

        Returns:
            {
                "success": True,
                "filename": "gdas1.nov25.w1",
                "local_path": "/path/to/file",
                "file_size": 12345678,
                "download_time": 15.3
            }
        """
        local_path = self.cache_dir / filename

        # 检查本地是否已有
        if local_path.exists() and not force_redownload:
            file_size = local_path.stat().st_size
            if file_size > 0:
                logger.info(
                    "file_already_exists",
                    filename=filename,
                    file_size=file_size
                )
                return {
                    "success": True,
                    "filename": filename,
                    "local_path": str(local_path),
                    "file_size": file_size,
                    "downloaded": False,
                    "message": "File already exists locally"
                }

        # 下载文件
        try:
            logger.info(
                "downloading_from_ftp",
                filename=filename,
                ftp_host=self.FTP_HOST
            )

            start_time = time.time()

            # 连接FTP
            ftp = ftplib.FTP(timeout=self.ftp_timeout)
            ftp.connect(self.FTP_HOST, 21)
            ftp.login()  # 匿名登录
            ftp.cwd(self.FTP_DIR)

            # 下载文件（二进制模式）
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {filename}', f.write)

            ftp.quit()

            download_time = time.time() - start_time
            file_size = local_path.stat().st_size

            logger.info(
                "download_success",
                filename=filename,
                file_size=file_size,
                download_time=round(download_time, 2)
            )

            return {
                "success": True,
                "filename": filename,
                "local_path": str(local_path),
                "file_size": file_size,
                "downloaded": True,
                "download_time": round(download_time, 2)
            }

        except ftplib.error_perm as e:
            logger.error(
                "ftp_permission_error",
                filename=filename,
                error=str(e)
            )
            return {
                "success": False,
                "filename": filename,
                "error": f"FTP permission error: {str(e)}",
                "error_type": "ftp_permission"
            }

        except Exception as e:
            logger.error(
                "download_failed",
                filename=filename,
                error=str(e)
            )

            # 清理部分下载的文件
            if local_path.exists():
                local_path.unlink()

            return {
                "success": False,
                "filename": filename,
                "error": str(e),
                "error_type": type(e).__name__
            }

    def download_for_timerange(
        self,
        start_time: datetime,
        end_time: datetime,
        force_redownload: bool = False
    ) -> Dict[str, Any]:
        """
        下载时间范围所需的所有GDAS文件

        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            force_redownload: 强制重新下载

        Returns:
            {
                "success": True,
                "files_required": 2,
                "files_downloaded": 1,
                "files_existing": 1,
                "files_failed": 0,
                "file_paths": ["/path/to/file1", ...],
                "download_results": [...]
            }
        """
        # 计算需要的文件
        required_files = self.get_required_files_for_timerange(start_time, end_time)

        # 检查本地可用性
        availability = self.check_local_availability(required_files)

        download_results = []
        file_paths = []
        downloaded_count = 0
        existing_count = 0
        failed_count = 0

        # 下载缺失的文件
        for filename in required_files:
            if not availability[filename] or force_redownload:
                result = self.download_file(filename, force_redownload)
                download_results.append(result)

                if result["success"]:
                    file_paths.append(result["local_path"])
                    if result.get("downloaded"):
                        downloaded_count += 1
                    else:
                        existing_count += 1
                else:
                    failed_count += 1
            else:
                # 文件已存在
                local_path = self.cache_dir / filename
                file_paths.append(str(local_path))
                existing_count += 1

        success = (failed_count == 0)

        logger.info(
            "download_for_timerange_completed",
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            files_required=len(required_files),
            files_downloaded=downloaded_count,
            files_existing=existing_count,
            files_failed=failed_count,
            success=success
        )

        return {
            "success": success,
            "files_required": len(required_files),
            "files_downloaded": downloaded_count,
            "files_existing": existing_count,
            "files_failed": failed_count,
            "file_paths": file_paths,
            "download_results": download_results
        }

    def get_file_paths_for_timerange(
        self,
        start_time: datetime,
        end_time: datetime,
        auto_download: bool = True
    ) -> List[str]:
        """
        获取时间范围所需的GDAS文件路径列表

        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            auto_download: 如果文件不存在，是否自动下载

        Returns:
            文件路径列表（完整路径）
        """
        required_files = self.get_required_files_for_timerange(start_time, end_time)
        availability = self.check_local_availability(required_files)

        # 如果有缺失文件且允许自动下载
        missing_files = [f for f, avail in availability.items() if not avail]
        if missing_files and auto_download:
            logger.info(
                "auto_downloading_missing_files",
                missing_count=len(missing_files)
            )
            download_result = self.download_for_timerange(start_time, end_time)

            if not download_result["success"]:
                logger.warning(
                    "auto_download_partial_failure",
                    failed_count=download_result["files_failed"]
                )

        # 返回存在的文件路径
        file_paths = []
        for filename in required_files:
            local_path = self.cache_dir / filename
            if local_path.exists():
                file_paths.append(str(local_path.absolute()))

        return file_paths

    def clean_old_cache(
        self,
        max_age_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        清理过期的缓存文件

        Args:
            max_age_days: 最大缓存天数（默认使用self.max_cache_days）

        Returns:
            {
                "files_deleted": 3,
                "space_freed": 123456789,
                "files_kept": 5
            }
        """
        if max_age_days is None:
            max_age_days = self.max_cache_days

        cutoff_time = time.time() - (max_age_days * 24 * 3600)

        files_deleted = 0
        space_freed = 0
        files_kept = 0

        for file_path in self.cache_dir.glob("gdas1.*"):
            if file_path.is_file():
                file_mtime = file_path.stat().st_mtime

                if file_mtime < cutoff_time:
                    # 删除过期文件
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    files_deleted += 1
                    space_freed += file_size

                    logger.debug(
                        "cache_file_deleted",
                        filename=file_path.name,
                        age_days=int((time.time() - file_mtime) / 86400)
                    )
                else:
                    files_kept += 1

        logger.info(
            "cache_cleanup_completed",
            files_deleted=files_deleted,
            space_freed_mb=round(space_freed / 1024 / 1024, 2),
            files_kept=files_kept
        )

        return {
            "files_deleted": files_deleted,
            "space_freed": space_freed,
            "files_kept": files_kept
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            {
                "total_files": 10,
                "total_size": 500000000,
                "oldest_file_date": "2025-10-15",
                "newest_file_date": "2025-11-19",
                "cache_dir": "/path/to/cache"
            }
        """
        files = list(self.cache_dir.glob("gdas1.*"))

        if not files:
            return {
                "total_files": 0,
                "total_size": 0,
                "oldest_file_date": None,
                "newest_file_date": None,
                "cache_dir": str(self.cache_dir)
            }

        total_size = sum(f.stat().st_size for f in files)

        file_mtimes = [f.stat().st_mtime for f in files]
        oldest_mtime = min(file_mtimes)
        newest_mtime = max(file_mtimes)

        oldest_date = datetime.fromtimestamp(oldest_mtime).strftime("%Y-%m-%d")
        newest_date = datetime.fromtimestamp(newest_mtime).strftime("%Y-%m-%d")

        return {
            "total_files": len(files),
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "oldest_file_date": oldest_date,
            "newest_file_date": newest_date,
            "cache_dir": str(self.cache_dir)
        }
