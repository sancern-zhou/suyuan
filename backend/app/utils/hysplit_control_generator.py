"""
HYSPLIT CONTROL File Generator

HYSPLIT CONTROL文件生成器
用于生成HYSPLIT模型的输入配置文件

CONTROL文件格式说明：
- Line 1: 起始时间（年 月 日 时，UTC）
- Line 2: 起始位置数量（通常为1）
- Line 3: 起始位置（纬度 经度 高度AGL）
- Line 4: 运行时长（小时，负数=后向，正数=正向）
- Line 5: 垂直运动方法（0=模型风场，1=等熵面，2=等密度面）
- Line 6: 模型顶部高度（米）
- Line 7: 气象文件数量
- Line 8+: 气象文件路径和文件名（每个文件2行）
- Last-2: 输出目录
- Last-1: 输出文件名
"""

from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
import structlog

logger = structlog.get_logger()


class HYSPLITControlGenerator:
    """
    HYSPLIT CONTROL文件生成器

    功能：
    - 生成后向轨迹CONTROL文件
    - 生成正向轨迹CONTROL文件
    - 支持多起始位置（未来扩展）
    - 支持多种垂直运动方法
    """

    def __init__(self):
        """初始化CONTROL生成器"""
        self.default_top_height = 10000.0  # 模型顶部10km
        self.default_vertical_method = 0    # 使用模型风场
        logger.info("hysplit_control_generator_initialized")

    def generate_backward_control(
        self,
        lat: float,
        lon: float,
        height: float,
        start_time: datetime,
        hours: int,
        meteo_dir: str,
        meteo_files: List[str],
        output_dir: str = "./",
        output_filename: str = "tdump"
    ) -> str:
        """
        生成后向轨迹CONTROL文件内容

        Args:
            lat: 起始纬度
            lon: 起始经度
            height: 起始高度（米，AGL）
            start_time: 轨迹起始时间（UTC）
            hours: 回溯小时数（正数，内部会转换为负数）
            meteo_dir: 气象数据目录
            meteo_files: 气象文件名列表
            output_dir: 输出目录
            output_filename: 输出文件名

        Returns:
            CONTROL文件内容字符串

        Example:
            >>> gen = HYSPLITControlGenerator()
            >>> control = gen.generate_backward_control(
            ...     lat=23.13,
            ...     lon=113.26,
            ...     height=100.0,
            ...     start_time=datetime(2024, 10, 1, 12, 0),
            ...     hours=72,
            ...     meteo_dir="data/meteo/gdas1/",
            ...     meteo_files=["gdas1.oct24.w1"]
            ... )
        """
        # 后向轨迹：运行时长为负数
        run_hours = -abs(hours)

        return self._generate_control(
            lat=lat,
            lon=lon,
            height=height,
            start_time=start_time,
            run_hours=run_hours,
            meteo_dir=meteo_dir,
            meteo_files=meteo_files,
            output_dir=output_dir,
            output_filename=output_filename
        )

    def generate_forward_control(
        self,
        lat: float,
        lon: float,
        height: float,
        start_time: datetime,
        hours: int,
        meteo_dir: str,
        meteo_files: List[str],
        output_dir: str = "./",
        output_filename: str = "tdump"
    ) -> str:
        """
        生成正向轨迹CONTROL文件内容

        Args:
            lat: 起始纬度（污染源）
            lon: 起始经度
            height: 起始高度（米，AGL）
            start_time: 轨迹起始时间（UTC）
            hours: 预测小时数（正数）
            meteo_dir: 气象数据目录
            meteo_files: 气象文件名列表
            output_dir: 输出目录
            output_filename: 输出文件名

        Returns:
            CONTROL文件内容字符串
        """
        # 正向轨迹：运行时长为正数
        run_hours = abs(hours)

        return self._generate_control(
            lat=lat,
            lon=lon,
            height=height,
            start_time=start_time,
            run_hours=run_hours,
            meteo_dir=meteo_dir,
            meteo_files=meteo_files,
            output_dir=output_dir,
            output_filename=output_filename
        )

    def _generate_control(
        self,
        lat: float,
        lon: float,
        height: float,
        start_time: datetime,
        run_hours: int,
        meteo_dir: str,
        meteo_files: List[str],
        output_dir: str,
        output_filename: str
    ) -> str:
        """
        内部方法：生成CONTROL文件内容

        Args:
            run_hours: 运行时长（负数=后向，正数=正向）

        Returns:
            CONTROL文件内容字符串
        """
        # 格式化起始时间（YY MM DD HH）
        year = start_time.year % 100  # 2位年份（24 for 2024）
        month = start_time.month
        day = start_time.day
        hour = start_time.hour

        # 构建CONTROL文件内容
        lines = []

        # Line 1: 起始时间
        lines.append(f"{year:2d} {month:2d} {day:2d} {hour:2d}")

        # Line 2: 起始位置数量
        lines.append("1")

        # Line 3: 起始位置（纬度 经度 高度）
        lines.append(f"{lat:.4f} {lon:.4f} {height:.1f}")

        # Line 4: 运行时长
        lines.append(f"{run_hours}")

        # Line 5: 垂直运动方法（0=模型风场）
        lines.append(f"{self.default_vertical_method}")

        # Line 6: 模型顶部高度
        lines.append(f"{self.default_top_height:.1f}")

        # Line 7: 气象文件数量
        lines.append(f"{len(meteo_files)}")

        # Line 8+: 气象文件（每个文件2行：目录 + 文件名）
        for meteo_file in meteo_files:
            lines.append(meteo_dir)      # 气象数据目录
            lines.append(meteo_file)      # 气象文件名

        # Last-2: 输出目录
        lines.append(output_dir)

        # Last-1: 输出文件名
        lines.append(output_filename)

        # 拼接为字符串（每行结尾加换行符）
        control_content = "\n".join(lines) + "\n"

        logger.debug(
            "control_file_generated",
            lat=lat,
            lon=lon,
            height=height,
            run_hours=run_hours,
            meteo_files_count=len(meteo_files)
        )

        return control_content

    def write_control_file(
        self,
        control_content: str,
        output_path: str
    ) -> None:
        """
        将CONTROL内容写入文件

        Args:
            control_content: CONTROL文件内容
            output_path: 输出文件路径
        """
        # 确保目录存在
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(control_content)

        logger.info(
            "control_file_written",
            output_path=output_path,
            file_size=len(control_content)
        )

    def generate_setup_cfg(
        self,
        tratio: float = 0.75,
        mgmin: int = 10,
        kmixd: int = 0,
        kmix0: int = 250,
        kdef: int = 0,
        kbls: int = 1,
        kblt: int = 2
    ) -> str:
        """
        生成SETUP.CFG文件内容

        SETUP.CFG控制HYSPLIT的高级参数：
        - tratio: 内部时间步长比例（0.75推荐）
        - mgmin: 最小网格尺寸（分钟）
        - kmixd: 混合深度计算方法（0=输入数据）
        - kmix0: 默认混合深度（米）
        - kdef: 水平插值方法（0=线性）
        - kbls: 边界层稳定度方法（1=Beljaars）
        - kblt: 边界层湍流方法（2=TKE）

        Returns:
            SETUP.CFG文件内容
        """
        lines = []

        lines.append("&SETUP")
        lines.append(f"tratio = {tratio},")
        lines.append(f"mgmin = {mgmin},")
        lines.append(f"kmixd = {kmixd},")
        lines.append(f"kmix0 = {kmix0},")
        lines.append(f"kdef = {kdef},")
        lines.append(f"kbls = {kbls},")
        lines.append(f"kblt = {kblt},")
        lines.append("/")

        return "\n".join(lines) + "\n"

    def write_setup_cfg(
        self,
        setup_content: str,
        output_path: str
    ) -> None:
        """
        将SETUP.CFG内容写入文件

        Args:
            setup_content: SETUP.CFG文件内容
            output_path: 输出文件路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(setup_content)

        logger.info(
            "setup_cfg_written",
            output_path=output_path
        )
