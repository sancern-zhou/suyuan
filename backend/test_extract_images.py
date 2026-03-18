#!/usr/bin/env python
"""Test extract_images functionality"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test_extract_images():
    """Test extracting images from a Word document"""
    from app.tools.office.word_tool import WordWin32LLMTool

    tool = WordWin32LLMTool()

    # Test with existing document
    test_doc = r"D:\溯源\backend\test_word.docx"

    print(f"Testing extract_images with: {test_doc}")
    print("=" * 80)

    result = await tool.execute(
        path=test_doc,
        operation="extract_images"
    )

    print(f"Status: {result.get('status')}")
    print(f"Success: {result.get('success')}")
    print(f"Summary: {result.get('summary')}")

    if result.get('success') and 'data' in result:
        data = result['data']
        if 'images' in data:
            print(f"\nExtracted {len(data['images'])} images:")
            for img in data['images']:
                print(f"\n  Image {img['index']}:")
                print(f"    Path: {img['path']}")
                print(f"    Size: {img['width']} x {img['height']}")

                # Verify file exists
                if Path(img['path']).exists():
                    file_size = Path(img['path']).stat().st_size
                    print(f"    File size: {file_size} bytes")
                else:
                    print(f"    ERROR: File not found!")

    print("\n" + "=" * 80)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_extract_images())
