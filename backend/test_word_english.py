# -*- coding: utf-8 -*-
"""
Test Word replacement with English text
"""

import sys
import time


def test_chinese_text():
    """Test replacement with Chinese text"""
    print("\n" + "=" * 80)
    print("Test 1: Chinese Text Replacement")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original text: {repr(doc.Content.Text)}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True
    find.Wrap = 1

    print(f"\nExecuting Find.Execute(Replace=2, ReplaceWith='')...")
    result = find.Execute(Replace=2, ReplaceWith="")
    print(f"Result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {repr(doc.Content.Text)}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return doc.Content.Text.count('41微克/立方米') == 0


def test_english_text():
    """Test replacement with English text"""
    print("\n" + "=" * 80)
    print("Test 2: English Text Replacement")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test TARGET ABC TARGET XYZ"

    print(f"Original text: {repr(doc.Content.Text)}")
    print(f"Count: {doc.Content.Text.count('TARGET')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "TARGET"
    find.Forward = True
    find.Wrap = 1

    print(f"\nExecuting Find.Execute(Replace=2, ReplaceWith='')...")
    result = find.Execute(Replace=2, ReplaceWith="")
    print(f"Result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {repr(doc.Content.Text)}")
    print(f"Count after: {doc.Content.Text.count('TARGET')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return doc.Content.Text.count('TARGET') == 0


def test_chinese_with_wildcards():
    """Test with wildcards enabled"""
    print("\n" + "=" * 80)
    print("Test 3: Chinese Text with Wildcards=False")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original text: {repr(doc.Content.Text)}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True
    find.Wrap = 1
    find.MatchWildcards = False  # Explicitly set to False

    print(f"\nMatchWildcards: {find.MatchWildcards}")
    print(f"Executing Find.Execute(Replace=2, ReplaceWith='')...")
    result = find.Execute(Replace=2, ReplaceWith="")
    print(f"Result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {repr(doc.Content.Text)}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return doc.Content.Text.count('41微克/立方米') == 0


def test_find_then_replace():
    """Test finding first, then replacing"""
    print("\n" + "=" * 80)
    print("Test 4: Find First, Then Replace")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original text: {repr(doc.Content.Text)}")

    # First find
    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True

    print(f"\nExecuting Find.Execute() (no replace)...")
    found = find.Execute()
    print(f"Found: {found}")

    if found:
        print(f"Found at position: {find.Parent.Start}-{find.Parent.End}")

        # Now replace
        print(f"\nExecuting replacement...")
        find.Execute(Replace=2, ReplaceWith="")
        print(f"After replace: {repr(doc.Content.Text)}")
        print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return doc.Content.Text.count('41微克/立方米') == 0


def main():
    print("Word Replacement Tests")
    print("=" * 80)

    results = {}

    try:
        results['chinese'] = test_chinese_text()
    except Exception as e:
        print(f"Chinese test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['english'] = test_english_text()
    except Exception as e:
        print(f"English test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['chinese_no_wildcards'] = test_chinese_with_wildcards()
    except Exception as e:
        print(f"No wildcards test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['find_then_replace'] = test_find_then_replace()
    except Exception as e:
        print(f"Find then replace test failed: {e}")
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
