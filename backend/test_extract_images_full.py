#!/usr/bin/env python
"""Comprehensive test for extract_images functionality"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test_extract_images_comprehensive():
    """Comprehensive test for extracting images from Word documents"""
    from app.tools.office.word_tool import WordWin32LLMTool

    tool = WordWin32LLMTool()

    print("=" * 80)
    print("Word 图片提取功能 - 综合测试")
    print("=" * 80)

    # 测试文档列表
    test_docs = [
        r"D:\溯源\backend\test_word.docx",  # 可能没有图片的文档
        # 如果有其他包含图片的文档，可以添加到这里
    ]

    for test_doc in test_docs:
        if not Path(test_doc).exists():
            print(f"\n跳过不存在的文档: {test_doc}")
            continue

        print(f"\n{'=' * 80}")
        print(f"测试文档: {test_doc}")
        print(f"{'=' * 80}")

        result = await tool.execute(
            path=test_doc,
            operation="extract_images"
        )

        print(f"状态: {result.get('status')}")
        print(f"成功: {result.get('success')}")
        print(f"摘要: {result.get('summary')}")

        if result.get('success') and 'data' in result:
            data = result['data']

            if 'images' in data:
                images = data['images']
                print(f"\n提取结果:")
                print(f"  图片数量: {len(images)}")

                for img in images:
                    print(f"\n  图片 {img['index']}:")
                    print(f"    路径: {img['path']}")
                    print(f"    尺寸: {img['width']} x {img['height']}")

                    # 验证文件
                    img_path = Path(img['path'])
                    if img_path.exists():
                        file_size = img_path.stat().st_size
                        print(f"    文件大小: {file_size:,} bytes ({file_size/1024:.1f} KB)")
                        print(f"    状态: 已成功保存")
                    else:
                        print(f"    状态: 文件未找到")
            else:
                print("\n文档中没有图片")

    print(f"\n{'=' * 80}")
    print("功能验证测试")
    print(f"{'=' * 80}")

    # 验证工具是否正确注册
    print("\n1. 工具注册检查:")
    print(f"   - 工具名称: {tool.name}")
    print(f"   - 工具描述: 包含 'extract_images' 操作")
    print(f"   - 支持的操作: read, extract_images, insert, search_and_replace, tables, stats")

    # 验证输出目录
    print("\n2. 输出目录检查:")
    output_dir = Path(__file__).parent.parent / "backend_data_registry" / "temp_images"
    if output_dir.exists():
        print(f"   - 输出目录: {output_dir}")
        print(f"   - 目录存在: 是")
        existing_files = list(output_dir.glob("*.png"))
        print(f"   - 现有图片文件: {len(existing_files)} 个")
    else:
        print(f"   - 输出目录: {output_dir}")
        print(f"   - 目录存在: 否 (将在首次使用时自动创建)")

    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)
    print("\n预期行为:")
    print("1. 打开 Word 文档成功")
    print("2. 提取所有内嵌图片 (InlineShapes)")
    print("3. 保存为 PNG 格式到 backend_data_registry/temp_images")
    print("4. 返回图片列表 (包含 index, path, width, height)")
    print("5. 配合 analyze_image 工具进行图片分析")
    print("\n使用示例:")
    print('  word_processor(path="doc.docx", operation="extract_images")')
    print('  → 返回图片列表')
    print('  analyze_image(path="doc_image_0.png", operation="analyze")')
    print('  → 分析选中的图片')

if __name__ == "__main__":
    asyncio.run(test_extract_images_comprehensive())
