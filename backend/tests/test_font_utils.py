"""
字体工具单元测试

运行方法：
    pytest tests/test_font_utils.py -v
"""

import pytest
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
import tempfile


class TestFontManager:
    """测试 FontManager 类"""

    def test_font_manager_singleton(self):
        """测试单例模式"""
        from app.utils.font_utils import get_font_manager, FontManager

        manager1 = get_font_manager()
        manager2 = get_font_manager()

        assert manager1 is manager2, "FontManager 应该是单例"
        assert isinstance(manager1, FontManager)

    def test_configure_chinese_font(self):
        """测试字体配置"""
        from app.utils.font_utils import configure_chinese_font

        # 配置字体
        success = configure_chinese_font()

        # 验证配置
        assert success, "字体配置应该成功"
        assert len(plt.rcParams['font.sans-serif']) > 0, "应该配置字体列表"
        assert plt.rcParams['axes.unicode_minus'] == False, "应该禁用 unicode minus"

    def test_get_available_fonts(self):
        """测试获取可用字体列表"""
        from app.utils.font_utils import FontManager

        manager = FontManager()
        fonts = manager._get_available_fonts()

        assert isinstance(fonts, list), "应该返回列表"
        assert len(fonts) > 0, "应该至少有一个可用字体"
        assert 'DejaVu Sans' in fonts, "应该有 DejaVu Sans 字体"

    def test_find_best_chinese_font(self):
        """测试查找最佳中文字体"""
        from app.utils.font_utils import FontManager

        manager = FontManager()
        font = manager._find_best_chinese_font()

        # 至少应该找到 DejaVu Sans（最后的回退）
        assert font is not None, "应该至少找到一个字体"

    def test_verify_font_support(self):
        """测试字体验证"""
        from app.utils.font_utils import FontManager

        manager = FontManager()
        manager.configure_chinese_font()

        result = manager.verify_font_support()

        assert isinstance(result, dict), "应该返回字典"
        assert 'configured' in result, "应该有 configured 字段"
        assert 'test_passed' in result, "应该有 test_passed 字段"


class TestChineseRendering:
    """测试中文渲染功能"""

    def test_simple_chinese_text(self):
        """测试简单中文文本渲染"""
        from app.utils.font_utils import configure_chinese_font

        configure_chinese_font()

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.set_title('中文标题测试')
        ax.set_xlabel('X轴标签')
        ax.set_ylabel('Y轴标签')

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name

        try:
            plt.savefig(temp_path, dpi=100, bbox_inches='tight')
            plt.close()

            # 验证文件存在
            assert Path(temp_path).exists(), "应该生成图片文件"
            assert Path(temp_path).stat().st_size > 0, "文件大小应该大于0"

        finally:
            # 清理
            Path(temp_path).unlink(missing_ok=True)

    def test_chinese_numbers(self):
        """测试中文和数字混合渲染"""
        from app.utils.font_utils import configure_chinese_font

        configure_chinese_font()

        fig, ax = plt.subplots(figsize=(6, 4))

        cities = ['广州', '深圳', '佛山', '东莞']
        values = [68, 52, 75, 71]

        bars = ax.bar(cities, values)

        # 添加数字标签
        for bar, v in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{v}', ha='center', va='bottom')

        ax.set_title('城市AQI对比（中文+数字测试）')

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name

        try:
            plt.savefig(temp_path, dpi=100, bbox_inches='tight')
            plt.close()

            assert Path(temp_path).exists()

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_scientific_notation(self):
        """测试科学计数法渲染"""
        from app.utils.font_utils import configure_chinese_font

        configure_chinese_font()

        fig, ax = plt.subplots(figsize=(6, 4))

        x = [1, 2, 3, 4, 5]
        y = [15, 52, 48, 38, 30]

        ax.plot(x, y, 'o-')
        ax.set_title('PM2.5 浓度变化')
        ax.set_ylabel('浓度 (μg/m³)')
        ax.set_xlabel('时间')

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name

        try:
            plt.savefig(temp_path, dpi=100, bbox_inches='tight')
            plt.close()

            assert Path(temp_path).exists()

        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestFontFallback:
    """测试字体回退机制"""

    def test_font_fallback_chain(self):
        """测试字体回退链"""
        from app.utils.font_utils import FontManager

        fallback_chain = FontManager.FONT_FALLBACK_CHAIN

        assert isinstance(fallback_chain, list), "回退链应该是列表"
        assert len(fallback_chain) > 0, "回退链不应该为空"
        assert 'DejaVu Sans' in fallback_chain, "应该有最后的回退字体"

    def test_font_file_paths(self):
        """测试字体文件路径"""
        from app.utils.font_utils import FontManager

        paths = FontManager.FONT_FILE_PATHS

        assert isinstance(paths, list), "字体路径应该是列表"
        assert all(isinstance(p, Path) for p in paths), "所有元素应该是 Path 对象"


@pytest.mark.integration
class TestIntegration:
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流"""
        from app.utils.font_utils import configure_chinese_font

        # 1. 配置字体
        configure_chinese_font()

        # 2. 创建复杂图表
        fig, axes = plt.subplots(2, 2, figsize=(10, 8))

        # 子图1：柱状图
        axes[0, 0].bar(['北京', '上海', '广州'], [50, 60, 70])
        axes[0, 0].set_title('城市AQI对比')

        # 子图2：折线图
        axes[0, 1].plot([1, 2, 3, 4], [10, 20, 15, 25], 'o-')
        axes[0, 1].set_title('月度变化趋势')

        # 子图3：饼图
        axes[1, 0].pie([25, 30, 20, 15], labels=['PM2.5', 'PM10', 'O₃', 'NO₂'],
                      autopct='%1.1f%%')
        axes[1, 0].set_title('污染物占比')

        # 子图4：散点图
        axes[1, 1].scatter([10, 20, 30, 40], [15, 25, 20, 35])
        axes[1, 1].set_title('相关性分析')

        plt.tight_layout()

        # 3. 保存图表
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name

        try:
            plt.savefig(temp_path, dpi=100, bbox_inches='tight')
            plt.close()

            # 4. 验证结果
            assert Path(temp_path).exists()
            assert Path(temp_path).stat().st_size > 10000  # 至少10KB

        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
