"""
字体工具模块 - 提供健壮的中文字体配置

设计理念：
1. 自动检测系统可用字体
2. 多层回退机制
3. 启动时验证，运行时零配置
4. 跨平台支持（Linux/Windows/macOS）
"""

import functools
import re

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path
from typing import Any, List, Optional
import logging

from app.utils.path_config import PROJECT_ROOT

logger = logging.getLogger(__name__)

_UNICODE_SUBSUP_RE = re.compile("[\u2070-\u209f\u00b2\u00b3\u00b9\u207a\u207b]")


def _normalize_dict_mapping_strs(mapping: Any, label_normalizer: Any) -> None:
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            if isinstance(value, str):
                mapping[key] = str(label_normalizer(value))


def _normalize_formatter_labels(formatter: Any, label_normalizer: Any) -> None:
    """归一化 formatter 内部保存的刻度标签序列。

    draw/savefig 时刻度文本由 formatter 重新生成，只改 Tick 的 Text 对象会被
    原始序列覆盖。matplotlib 3.9 的 set_xticklabels 用
    FuncFormatter(functools.partial(_format_with_dict, {位置: 标签})) 保存标签，
    旧版本/其他路径用 FixedFormatter.seq，这里两种载体都处理。
    """
    seq = getattr(formatter, "seq", None)
    if isinstance(seq, list):
        formatter.seq = [str(label_normalizer(item)) if isinstance(item, str) else item for item in seq]
    func = getattr(formatter, "func", None)
    if isinstance(func, functools.partial):
        for arg in func.args:
            _normalize_dict_mapping_strs(arg, label_normalizer)
        for value in (func.keywords or {}).values():
            _normalize_dict_mapping_strs(value, label_normalizer)


def normalize_figure_text(fig: Any, label_normalizer: Any) -> List[str]:
    """按 label_normalizer 归一化图中所有文本，返回仍含 Unicode 上下标的残留文本。

    除普通 Text 对象外，必须同时处理坐标轴 formatter 的内部序列：
    draw/savefig 时刻度文本由 formatter 重新生成，只改 Text 对象会被
    原始序列覆盖，Unicode 下标黑框问题会复发。
    残留字符说明当前字体缺字形，渲染时会显示为黑色矩形（tofu）。
    """
    residual: List[str] = []
    try:
        for text in fig.findobj(match=matplotlib.text.Text):
            original = text.get_text()
            try:
                normalized = str(label_normalizer(original))
                if normalized != original:
                    text.set_text(normalized)
            except Exception:
                pass
            current = text.get_text()
            if isinstance(current, str) and _UNICODE_SUBSUP_RE.search(current):
                residual.append(current)
    except Exception:
        pass
    try:
        for ax in fig.axes:
            for axis in (ax.xaxis, ax.yaxis):
                for formatter in (axis.get_major_formatter(), axis.get_minor_formatter()):
                    _normalize_formatter_labels(formatter, label_normalizer)
    except Exception:
        pass
    if residual:
        logger.warning(f"normalize_figure_text 残留 Unicode 上下标字符，可能渲染为黑框: {residual}")
    return residual

BROWSER_CHART_FONT_FAMILY = (
    "FZXiaoBiaoSong-B05S, 方正小标宋简体, PingFang SC, Hiragino Sans GB, "
    "Microsoft YaHei, Noto Sans CJK SC, Helvetica Neue, Arial, sans-serif"
)


class FontManager:
    """字体管理器 - 自动配置中文字体"""

    # 字体配置优先级（从高到低）
    FONT_FALLBACK_CHAIN = [
        'FZXiaoBiaoSong-B05S',  # 方正小标宋，create_business_chart优先字体
        'GB_XBS_GB18030',       # 国标小标宋，Linux部署常见小标宋字体
        'GB_XBS_GBT2312',
        # Linux 系统字体
        'Noto Sans CJK SC',     # 简体中文（推荐）
        'Noto Sans CJK TC',     # 繁体中文
        'Noto Sans CJK JP',     # 日文（也支持简体）
        'Noto Serif CJK SC',
        'WenQuanYi Micro Hei',  # 文泉驿微米黑
        'WenQuanYi Zen Hei',    # 文泉驿正黑
        # Windows 系统字体
        'Microsoft YaHei',      # 微软雅黑
        'SimHei',               # 黑体
        'SimSun',               # 宋体
        # macOS 系统字体
        'PingFang SC',          # 苹方-简体中文
        'Heiti SC',             # 黑体-简
        'STHeiti',              # 华文黑体
        # 通用回退
        'DejaVu Sans',
        'sans-serif',
    ]

    # 字体文件路径（Linux）
    FONT_FILE_PATHS = [
        PROJECT_ROOT / 'frontend/public/fonts/FZXiaoBiaoSong-B05S.ttf',
        Path('/home/xckj/.local/share/fonts/方正小标宋简.TTF'),
        Path('/usr/share/fonts/gb-cjk/GB_XBS_GB18030.TTF'),
        Path('/usr/share/fonts/gb-cjk/GB_XBS_GBT2312.TTF'),
        Path('/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf'),
        Path('/usr/share/fonts/google-droid-sans-fonts/DroidSansFallbackFull.ttf'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/arphic/uming.ttc'),
        Path('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'),
    ]

    def __init__(self):
        self._configured = False
        self._available_fonts = self._get_available_fonts()

    def _get_available_fonts(self) -> List[str]:
        """获取系统中所有可用的字体名称"""
        try:
            font_names = [f.name for f in fm.fontManager.ttflist]
            return list(set(font_names))  # 去重
        except Exception as e:
            logger.warning(f"获取字体列表失败: {e}")
            return []

    def _find_best_chinese_font(self) -> Optional[str]:
        """从系统中找到最佳的中文字体"""
        for font_name in self.FONT_FALLBACK_CHAIN:
            if font_name in self._available_fonts:
                logger.info(f"找到可用字体: {font_name}")
                return font_name
        return None

    def _register_font_files(self) -> None:
        """尝试注册字体文件"""
        for font_path in self.FONT_FILE_PATHS:
            if font_path.exists():
                try:
                    fm.fontManager.addfont(str(font_path))
                    font_prop = fm.FontProperties(fname=str(font_path))
                    font_name = font_prop.get_name()
                    logger.info(f"成功注册字体文件: {font_path} -> {font_name}")
                except Exception as e:
                    logger.debug(f"注册字体文件失败 {font_path}: {e}")
                    continue
        self._available_fonts = self._get_available_fonts()

    def preferred_font_name(self) -> Optional[str]:
        """Return the first installed family from the configured priority chain."""
        self._register_font_files()
        return self._find_best_chinese_font()

    def configure_chinese_font(self) -> bool:
        """
        配置中文字体（自动检测+多层回退）

        Returns:
            bool: 是否配置成功
        """
        if self._configured:
            return True

        logger.info("开始配置中文字体...")

        font_name = self.preferred_font_name()

        # 方法3：使用默认回退（即使不可用也设置，matplotlib会自动回退）
        if not font_name:
            logger.warning("未找到合适的中文字体，使用默认配置")
            font_name = self.FONT_FALLBACK_CHAIN[0]

        # 应用字体配置
        try:
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = [font_name] + self.FONT_FALLBACK_CHAIN[1:]
            plt.rcParams['axes.unicode_minus'] = False
            plt.rcParams['mathtext.fontset'] = 'dejavusans'
            plt.rcParams['mathtext.default'] = 'it'

            # 配置字体大小
            plt.rcParams['axes.titlesize'] = 12
            plt.rcParams['axes.labelsize'] = 11
            plt.rcParams['xtick.labelsize'] = 10
            plt.rcParams['ytick.labelsize'] = 10
            plt.rcParams['font.size'] = 10

            self._configured = True
            logger.info(f"✅ 中文字体配置成功: {font_name}")
            return True

        except Exception as e:
            logger.error(f"字体配置失败: {e}")
            return False

    def verify_font_support(self) -> dict:
        """
        验证字体支持情况（用于测试）

        Returns:
            dict: 验证结果
        """
        result = {
            'configured': self._configured,
            'available_chinese_fonts': [],
            'current_font': plt.rcParams['font.sans-serif'][0] if plt.rcParams['font.sans-serif'] else None,
            'test_passed': False
        }

        # 检查可用的中文字体
        for font_name in self.FONT_FALLBACK_CHAIN[:5]:  # 只检查前5个
            if font_name in self._available_fonts:
                result['available_chinese_fonts'].append(font_name)

        # 测试中文渲染
        try:
            import matplotlib
            matplotlib.use('Agg')
            fig, ax = plt.subplots(figsize=(1, 1))
            ax.text(0.5, 0.5, '测试中文123', fontsize=12)
            ax.set_axis_off()
            import tempfile
            temp_path = tempfile.mktemp(suffix='.png')
            plt.savefig(temp_path, dpi=50, bbox_inches='tight')
            plt.close()
            Path(temp_path).unlink(missing_ok=True)
            result['test_passed'] = True
        except Exception as e:
            result['test_error'] = str(e)

        return result


# 全局单例
_font_manager_instance = None

def get_font_manager() -> FontManager:
    """获取字体管理器单例"""
    global _font_manager_instance
    if _font_manager_instance is None:
        _font_manager_instance = FontManager()
    return _font_manager_instance


def configure_chinese_font() -> bool:
    """快捷函数：配置中文字体"""
    return get_font_manager().configure_chinese_font()


def select_preferred_chinese_font_path() -> Path | None:
    """Return the first available preferred Chinese font file path."""
    font_manager = get_font_manager()
    for font_path in font_manager.FONT_FILE_PATHS:
        if font_path.exists():
            return font_path
    return None


def chinese_font_prop() -> fm.FontProperties | None:
    """Return the preferred Chinese font, aligned with create_business_chart."""
    font_manager = get_font_manager()
    for font_path in font_manager.FONT_FILE_PATHS:
        if not font_path.exists():
            continue
        try:
            fm.fontManager.addfont(str(font_path))
            return fm.FontProperties(fname=str(font_path))
        except Exception as exc:
            logger.debug(f"注册字体文件失败 {font_path}: {exc}")
    font_name = font_manager._find_best_chinese_font()
    if font_name:
        return fm.FontProperties(family=[font_name])
    return None


def apply_font_to_figure(fig: Any, label_normalizer: Any = None) -> None:
    """Apply the configured Chinese font to all text objects in a matplotlib figure."""
    if label_normalizer is not None:
        normalize_figure_text(fig, label_normalizer)
    prop = chinese_font_prop()
    if prop is None:
        return
    for text in fig.findobj(match=matplotlib.text.Text):
        current_size = text.get_fontsize()
        text.set_fontproperties(prop)
        text.set_fontsize(current_size)


# 自动配置（模块导入时执行）
configure_chinese_font()
