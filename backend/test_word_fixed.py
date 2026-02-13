# -*- coding: utf-8 -*-
"""
Test the FIXED replacement method (manual delete + insert)
"""

import sys
import time


def test_fixed_method():
    """Test using manual delete + insert approach"""
    print("\n" + "=" * 80)
    print("Test: FIXED Method (Manual Delete + Insert)")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    test_content = """Test Document

Air Quality Data:
- O3_8h = 41 ug/m3
- PM2.5 = 35 ug/m3

Other info:
- 41微克/立方米 value #1
- 41微克/立方米 value #2
- 41微克/立方米 value #3
"""
    doc.Content.Text = test_content

    print(f"Original text (first 200 chars):\n{doc.Content.Text[:200]}")
    print(f"\nCount of '41微克/立方米': {doc.Content.Text.count('41微克/立方米')}")

    search_text = "41微克/立方米"
    replace_text = ""

    # 【FIXED METHOD】Manual find and replace
    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = search_text
    find.Forward = True
    find.Wrap = 1
    find.MatchCase = False
    find.MatchWholeWord = False
    find.MatchWildcards = False

    matches = []
    replacements = 0

    print(f"\nExecuting manual replacement loop...")
    while find.Execute():
        # Found match
        matched_range = doc.Range(find.Parent.Start, find.Parent.End)
        matched_text = matched_range.Text
        matches.append(matched_text.strip())
        print(f"  Match #{len(matches)}: {repr(matched_text[:50])}")

        # Delete found text
        matched_range.Delete()

        # Insert replacement text (if any)
        if replace_text:
            matched_range.InsertAfter(replace_text)

        replacements += 1

        # Reset position to avoid infinite loop
        find.Parent.Start = matched_range.End
        find.Parent.End = doc.Content.End

    print(f"\nTotal replacements: {replacements}")
    print(f"Modified text (first 200 chars):\n{doc.Content.Text[:200]}")
    print(f"\nCount after replacement: {doc.Content.Text.count('41微克/立方米')}")

    success = doc.Content.Text.count('41微克/立方米') == 0
    print(f"\n{'SUCCESS' if success else 'FAILED'}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return success


def test_fixed_method_with_save():
    """Test fixed method with actual file save"""
    print("\n" + "=" * 80)
    print("Test: FIXED Method with File Save")
    print("=" * 80)

    import win32com.client
    import os

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

    test_file = r"D:\溯源\backend\test_word_fixed.docx"

    print(f"Saving to: {test_file}")
    doc.SaveAs(test_file)

    print(f"Original count of '41微克/立方米': {doc.Content.Text.count('41微克/立方米')}")

    # Perform replacement
    search_text = "41微克/立方米"
    replace_text = ""

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = search_text
    find.Forward = True
    find.Wrap = 1

    replacements = 0
    while find.Execute():
        matched_range = doc.Range(find.Parent.Start, find.Parent.End)
        matched_range.Delete()
        if replace_text:
            matched_range.InsertAfter(replace_text)
        replacements += 1
        find.Parent.Start = matched_range.End
        find.Parent.End = doc.Content.End

    print(f"Replacements made: {replacements}")

    # Save the document
    doc.Save()
    print(f"Document saved")

    # Close and reopen to verify
    doc.Close(SaveChanges=0)
    time.sleep(2)

    doc2 = word.Documents.Open(test_file)
    reopened_count = doc2.Content.Text.count('41微克/立方米')
    print(f"Count in reopened file: {reopened_count}")

    success = reopened_count == 0
    print(f"\n{'SUCCESS' if success else 'FAILED'}")

    doc2.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    # Cleanup
    try:
        if os.path.exists(test_file):
            os.remove(test_file)
    except:
        pass

    return success


def main():
    print("Testing FIXED Word Replacement Method")
    print("=" * 80)

    results = {}

    try:
        results['fixed_in_memory'] = test_fixed_method()
    except Exception as e:
        print(f"Fixed method (in-memory) failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['fixed_with_save'] = test_fixed_method_with_save()
    except Exception as e:
        print(f"Fixed method (with save) failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Summary:")
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")

    return all(results.values())


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
