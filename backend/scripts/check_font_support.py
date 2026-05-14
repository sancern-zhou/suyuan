#!/usr/bin/env python3
"""
字体支持检测脚本

使用方法：
    python scripts/check_font_support.py

输出：
    - 系统中可用的中文字体列表
    - matplotlib 字体配置状态
    - 中文渲染测试结果
"""

import sys
from pathlib import Path

# 添加项目路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.utils.font_utils import FontManager, configure_chinese_font


def print_section(title: str):
    """打印分隔符"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    print_section("中文字体支持检测")

    # 1. 创建字体管理器
    font_manager = FontManager()

    # 2. 配置字体
    print("⚙️  正在配置中文字体...")
    success = font_manager.configure_chinese_font()

    if success:
        print("✅ 字体配置成功！")
    else:
        print("❌ 字体配置失败！")

    # 3. 显示可用字体
    print_section("可用的中文字体")
    available = []
    for font_name in FontManager.FONT_FALLBACK_CHAIN:
        if font_name in font_manager._available_fonts:
            available.append(font_name)
            print(f"  ✅ {font_name}")
        else:
            print(f"  ❌ {font_name}")

    if not available:
        print("\n⚠️  警告：系统中没有找到中文字体！")
        print("\n📥 安装建议：")
        print("   sudo apt install fonts-noto-cjk")
        print("   # 或")
        print("   sudo apt install fonts-wqy-microhei")

    # 4. 显示当前配置
    print_section("当前字体配置")
    import matplotlib.pyplot as plt
    print(f"  当前字体: {plt.rcParams['font.sans-serif'][0]}")
    print(f"  Unicode minus: {plt.rcParams['axes.unicode_minus']}")
    print(f"  Math fontset: {plt.rcParams['mathtext.fontset']}")

    # 5. 运行测试
    print_section("中文渲染测试")
    result = font_manager.verify_font_support()

    if result['test_passed']:
        print("✅ 中文渲染测试通过！")
        print("\n📊 测试图表已生成并验证")
    else:
        print("❌ 中文渲染测试失败！")
        if 'test_error' in result:
            print(f"   错误: {result['test_error']}")

    # 6. 总结
    print_section("检测结果总结")
    if success and result['test_passed']:
        print("✅ 系统字体配置正常，可以正常显示中文和数字！")
        return 0
    else:
        print("⚠️  系统字体配置存在问题，建议安装中文字体")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
