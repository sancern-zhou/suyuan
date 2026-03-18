"""
测试 Word 长文本替换（超过255字符）

验证修复：
1. 短文本替换（< 255字符）使用 wdReplaceAll
2. 长文本替换（> 255字符）使用先删除后插入
"""
import asyncio
import shutil
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

logger = structlog.get_logger()


async def test_short_text_replace():
    """测试短文本替换（< 255字符）"""
    word = WordWin32Tool(visible=False)

    original_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"
    test_file = r"D:\溯源\报告模板\test_short_replace.docx"

    # 复制文件
    shutil.copy2(original_file, test_file)
    print(f"✅ 创建测试副本: {test_file}")

    # 短文本替换（< 255字符）
    short_text = "【短替换】这是一段测试文本，用于验证短文本替换功能。"  # 约30字符

    print(f"\n{'='*60}")
    print(f"测试短文本替换（{len(short_text)}字符）")
    print(f"{'='*60}\n")

    result = word.search_and_replace(
        file_path=test_file,
        search_text="小结：",
        replace_text=short_text,
        match_case=False
    )

    print(f"替换状态: {result['status']}")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    # 验证
    result_read = word.read_all_text(test_file)
    if result_read['status'] == 'success' and short_text in result_read['text']:
        print(f"✅ 短文本替换成功！")
    else:
        print(f"❌ 短文本替换失败！")

    word.close_app()

    # 清理
    Path(test_file).unlink(missing_ok=True)


async def test_long_text_replace():
    """测试长文本替换（> 255字符）"""
    word = WordWin32Tool(visible=False)

    original_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"
    test_file = r"D:\溯源\报告模板\test_long_replace.docx"

    # 复制文件
    shutil.copy2(original_file, test_file)
    print(f"\n✅ 创建测试副本: {test_file}")

    # 长文本替换（> 255字符）
    long_text = """
    【长替换】这是第一段内容，用于测试长文本替换功能。

    根据监测数据显示，2025年11月2日当天，成都市城区空气质量监测点记录如下数据：
    - SO2浓度为4 μg/m³
    - NO2为24 μg/m³
    - CO为0.5 mg/m³
    - O3_8h为44 μg/m³
    - PM2.5为25 μg/m³
    - PM10为35 μg/m³
    - AQI为36

    气象条件为晴天，最高气温18.3℃，平均湿度69.4%，
    风向为西偏南风，平均风速0.9 m/s，紫外线辐射量为323.631 W/m²。

    这是第三段内容，继续填充文本以确保超过255字符限制。
    通过这次测试，我们可以验证长文本替换功能是否正常工作。
    """  # 约400字符

    print(f"\n{'='*60}")
    print(f"测试长文本替换（{len(long_text)}字符）")
    print(f"{'='*60}\n")

    result = word.search_and_replace(
        file_path=test_file,
        search_text="小结：",
        replace_text=long_text,
        match_case=False
    )

    print(f"替换状态: {result['status']}")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")
    else:
        # 验证
        result_read = word.read_all_text(test_file)
        if result_read['status'] == 'success' and "【长替换】" in result_read['text']:
            print(f"✅ 长文本替换成功！")
        else:
            print(f"❌ 长文本替换失败！")

    word.close_app()

    # 清理
    Path(test_file).unlink(missing_ok=True)


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Word 长文本替换测试套件")
    print("="*60)

    await test_short_text_replace()
    await test_long_text_replace()

    print("\n" + "="*60)
    print("所有测试完成！")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
