# -*- coding: utf-8 -*-
"""
Test if the search text matches document content
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.tools.office.word_win32_tool import WordWin32Tool


def main():
    print("=" * 80)
    print("Testing Search Text Matching")
    print("=" * 80)

    test_file = r"D:\溯源\报告模板\2025年臭氧垂直报告7-ok - 副本.docx"

    # Read document content
    print("\n[1] Reading document content...")
    tool = WordWin32Tool(visible=False)
    result = tool.read_all_text(test_file)

    if result.get("status") != "success":
        print(f"ERROR: {result.get('error')}")
        return False

    content = result.get("text", "")

    # Test different search texts
    search_texts = [
        "41 μg/m³",           # Original from log (with space, mu symbol)
        "41μg/m³",            # Without space
        "41 ug/m³",           # With "ug" instead of "μg"
        "41微克/立方米",       # Chinese
        "41 微克/立方米",      # Chinese with space
    ]

    print("\n[2] Testing different search texts:")
    print("-" * 80)

    for search_text in search_texts:
        count = content.count(search_text)
        print(f"Search: '{search_text}'")
        print(f"  Found: {count} times")
        print(f"  repr: {repr(search_text)}")

        # Find actual occurrences
        if search_text in content:
            idx = content.find(search_text)
            context = content[max(0, idx-30):idx+len(search_text)+30]
            print(f"  Context: ...{repr(context)}...")
        print()

    # Show a sample of the document
    print("\n[3] Document sample (first 500 chars):")
    print("-" * 80)
    print(content[:500])
    print()

    # Look for the actual pattern
    print("\n[4] Searching for patterns with '41' and '微克' or 'ug':")
    print("-" * 80)

    import re
    patterns = [
        r'41[^a-zA-Z0-9]*微克[^a-zA-Z0-9]*立方米',
        r'41[^a-zA-Z0-9]*μg/m³',
        r'41[^a-zA-Z0-9]*ug/m³',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"Pattern: {pattern}")
            print(f"  Found: {len(matches)} matches")
            for match in matches[:3]:  # Show first 3
                print(f"  - {repr(match)}")
            print()

    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
