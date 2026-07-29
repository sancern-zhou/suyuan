"""
字体工具模块 - 提供健壮的中文字体配置

设计理念：
1. 自动检测系统可用字体
2. 多层回退机制
3. 启动时验证，运行时零配置
4. 跨平台支持（Linux/Windows/macOS）
"""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path
from typing import Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class FontManager:
    """字体管理器 - 自动配置中文字体"""

    # 字体配置优先级（从高到低）
    FONT_FALLBACK_CHAIN = [
        'FZXiaoBiaoSong-B05S',  # 方正小标宋，create_report_chart优先字体
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
        Path('/home/xckj/.local/share/fonts/方正小标宋简.TTF'),
        Path('/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'),
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

    def _register_font_files(self) -> Optional[str]:
        """尝试注册字体文件"""
        for font_path in self.FONT_FILE_PATHS:
            if font_path.exists():
                try:
                    fm.fontManager.addfont(str(font_path))
                    font_prop = fm.FontProperties(fname=str(font_path))
                    font_name = font_prop.get_name()
                    logger.info(f"成功注册字体文件: {font_path} -> {font_name}")
                    return font_name
                except Exception as e:
                    logger.debug(f"注册字体文件失败 {font_path}: {e}")
                    continue
        return None

    def configure_chinese_font(self) -> bool:
        """
        配置中文字体（自动检测+多层回退）

        Returns:
            bool: 是否配置成功
        """
        if self._configured:
            return True

        logger.info("开始配置中文字体...")

        # 方法1：尝试注册字体文件
        font_name = self._register_font_files()

        # 方法2：从系统字体中查找
        if not font_name:
            font_name = self._find_best_chinese_font()

        # 方法3：使用默认回退（即使不可用也设置，matplotlib会自动回退）
        if not font_name:
            logger.warning("未找到合适的中文字体，使用默认配置")
            font_name = self.FONT_FALLBACK_CHAIN[0]

        # 应用字体配置
        try:
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


def chinese_font_prop() -> fm.FontProperties | None:
    """Return the preferred Chinese font, aligned with create_report_chart."""
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


def apply_font_to_figure(fig: Any) -> None:
    """Apply the configured Chinese font to all text objects in a matplotlib figure."""
    prop = chinese_font_prop()
    if prop is None:
        return
    for text in fig.findobj(match=matplotlib.text.Text):
        text.set_fontproperties(prop)


# 自动配置（模块导入时执行）
configure_chinese_font()
