# -*- coding: utf-8 -*-
"""
Test using Selection.Find instead of Range.Find
"""

import sys
import time


def test_selection_find():
    """Test using Selection.Find"""
    print("\n" + "=" * 80)
    print("Test: Using Selection.Find")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {repr(doc.Content.Text)}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    # Select all content
    doc.Content.Select()
    selection = word.Selection

    find = selection.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True
    find.Wrap = 1

    print(f"\nExecuting Selection.Find.Execute(Replace=2, ReplaceWith='')...")
    result = find.Execute(Replace=2, ReplaceWith="")
    print(f"Result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {repr(doc.Content.Text)}")
    count = doc.Content.Text.count('41微克/立方米')
    print(f"Count after: {count}")

    success = count == 0
    print(f"{'SUCCESS' if success else 'FAILED'}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return success


def test_replace_method():
    """Test using Range.Replace method"""
    print("\n" + "=" * 80)
    print("Test: Using Range.Replace method")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {repr(doc.Content.Text)}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    print(f"\nExecuting Content.Replace('41微克/立方米', '')...")
    try:
        # Range.Replace(FindText, ReplaceWith, Replace)
        # Replace: 0=none, 1=one, 2=all
        count = doc.Content.Replace("41微克/立方米", "", 2)
        print(f"Replace returned: {count} (type: {type(count).__name__})")

        print(f"After Replace: {repr(doc.Content.Text)}")
        new_count = doc.Content.Text.count('41微克/立方米')
        print(f"Count after: {new_count}")

        success = new_count == 0
        print(f"{'SUCCESS' if success else 'FAILED'}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return success


def test_simple_replace():
    """Test simplest possible replacement"""
    print("\n" + "=" * 80)
    print("Test: Simplest Replacement (delete text)")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test ABC Test"

    print(f"Original: {repr(doc.Content.Text)}")

    # Find and delete manually
    find = doc.Content.Find
    find.Text = "ABC"

    if find.Execute():
        print(f"Found 'ABC' at position {find.Parent.Start}-{find.Parent.End}")
        # Delete the found text
        find.Parent.Delete()
        print(f"After Delete: {repr(doc.Content.Text)}")
        success = "ABC" not in doc.Content.Text
        print(f"{'SUCCESS' if success else 'FAILED'}")
    else:
        print("Not found")
        success = False

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return success


def main():
    print("Word Replacement Method Tests")
    print("=" * 80)

    results = {}

    try:
        results['selection_find'] = test_selection_find()
    except Exception as e:
        print(f"Selection.Find test failed: {e}")

    try:
        results['replace_method'] = test_replace_method()
    except Exception as e:
        print(f"Replace method test failed: {e}")

    try:
        results['simple_replace'] = test_simple_replace()
    except Exception as e:
        print(f"Simple replace test failed: {e}")

    print("\n" + "=" * 80)
    print("Summary:")
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")

    return any(results.values())


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
