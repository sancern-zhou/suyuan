# -*- coding: utf-8 -*-
"""
Minimal Word replace test
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.tools.office.word_win32_tool import WordWin32Tool


def main():
    print("=" * 80)
    print("Word Search/Replace Test")
    print("=" * 80)

    # Create test doc
    print("\n[Step 1] Creating test document...")
    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Add()
    doc.Content.Text = """Test Document

Air Quality Data:
- O3_8h = 41 ug/m3
- PM2.5 = 35 ug/m3

Other info:
- 41微克/立方米 value #1
- 41微克/立方米 value #2
- 41微克/立方米 value #3
"""
    test_file = r"D:\溯源\backend\test_word.docx"
    doc.SaveAs(test_file)
    doc.Close()
    word.Quit()

    print(f"Created: {test_file}")

    # Read original
    print("\n[Step 2] Reading original content...")
    tool = WordWin32Tool(visible=False)
    result = tool.read_all_text(test_file)

    if result.get("status") != "success":
        print(f"ERROR: {result.get('error')}")
        return False

    original_text = result.get("text", "")
    print(f"Original text (first 200 chars):\n{original_text[:200]}")

    search_text = "41微克/立方米"
    original_count = original_text.count(search_text)
    print(f"\nOriginal count of '{search_text}': {original_count}")

    # Replace
    print(f"\n[Step 3] Searching and replacing...")
    print(f"Search: '{search_text}' -> Replace: ''")

    result = tool.search_and_replace(
        file_path=test_file,
        search_text=search_text,
        replace_text="",
        match_case=False,
        match_whole_word=False,
        use_wildcards=False
    )

    print(f"\nReplace result:")
    print(f"  status: {result.get('status')}")
    print(f"  replacements: {result.get('replacements')} (type: {type(result.get('replacements')).__name__})")
    print(f"  output_file: {result.get('output_file')}")
    print(f"  summary: {result.get('summary')}")

    # Wait for Word
    import time
    print("\n[Step 4] Waiting for Word to save...")
    time.sleep(3)

    # Read new content
    print("\n[Step 5] Reading modified content...")
    result = tool.read_all_text(test_file)

    if result.get("status") != "success":
        print(f"ERROR: {result.get('error')}")
        return False

    new_text = result.get("text", "")
    print(f"Modified text (first 200 chars):\n{new_text[:200]}")

    new_count = new_text.count(search_text)
    print(f"\nModified count of '{search_text}': {new_count}")

    # Compare
    print("\n[Step 6] Analysis...")
    print("=" * 80)

    if new_count == 0:
        print("SUCCESS: All target text removed")
        print(f"  {original_count} -> {new_count}")
        success = True
    elif new_count < original_count:
        print(f"PARTIAL: {original_count - new_count}/{original_count} removed")
        success = False
    else:
        print("FAILED: Document NOT modified!")
        print(f"  {original_count} -> {new_count}")

        if original_text == new_text:
            print("\nWARNING: Content is EXACTLY the same!")
            print(f"  Original length: {len(original_text)}")
            print(f"  New length: {len(new_text)}")
            print(f"  Difference: {len(original_text) - len(new_text)} chars")

            # Check file modification time
            mtime = os.path.getmtime(test_file)
            import time
            print(f"  File mtime: {time.ctime(mtime)}")

        success = False

    # Cleanup
    print("\n[Step 7] Cleanup...")
    try:
        if os.path.exists(test_file):
            os.remove(test_file)
        print("Cleanup complete")
    except Exception as e:
        print(f"Cleanup failed: {e}")

    print("=" * 80)
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
