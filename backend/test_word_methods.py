# -*- coding: utf-8 -*-
"""
Test different Word COM API replacement methods
"""

import sys
import time


def test_method_1():
    """Test using Find.Execute with Replace parameter"""
    print("\n" + "=" * 80)
    print("Method 1: find.Execute(Replace=2)")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {doc.Content.Text}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True

    result = find.Execute(Replace=2)  # wdReplaceAll
    print(f"Execute result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {doc.Content.Text}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return result


def test_method_2():
    """Test using Find.Execute with ReplaceWith parameter"""
    print("\n" + "=" * 80)
    print("Method 2: find.Execute(ReplaceWith='', Replace=2)")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {doc.Content.Text}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"

    result = find.Execute(ReplaceWith="", Replace=2)
    print(f"Execute result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {doc.Content.Text}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return result


def test_method_3():
    """Test using Replacement property"""
    print("\n" + "=" * 80)
    print("Method 3: find.Replacement.Text = ''")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {doc.Content.Text}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Replacement.ClearFormatting()
    find.Replacement.Text = ""

    result = find.Execute(Replace=2)
    print(f"Execute result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {doc.Content.Text}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return result


def test_method_4():
    """Test using wdReplaceAll constant"""
    print("\n" + "=" * 80)
    print("Method 4: Using explicit wdReplaceAll constant")
    print("=" * 80)

    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = "Test 41微克/立方米 ABC 41微克/立方米 XYZ"

    print(f"Original: {doc.Content.Text}")
    print(f"Count: {doc.Content.Text.count('41微克/立方米')}")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = "41微克/立方米"
    find.Forward = True
    find.Wrap = 1  # wdFindContinue

    # wdReplaceAll = 2
    result = find.Execute(Replace=2, ReplaceWith="")
    print(f"Execute result: {result} (type: {type(result).__name__})")

    print(f"After Execute: {doc.Content.Text}")
    print(f"Count after: {doc.Content.Text.count('41微克/立方米')}")

    doc.Close(SaveChanges=0)
    word.Quit()
    time.sleep(2)

    return result


def main():
    print("Testing Word COM API Replacement Methods")
    print("=" * 80)

    results = {}

    try:
        results['method1'] = test_method_1()
    except Exception as e:
        print(f"Method 1 failed: {e}")

    try:
        results['method2'] = test_method_2()
    except Exception as e:
        print(f"Method 2 failed: {e}")

    try:
        results['method3'] = test_method_3()
    except Exception as e:
        print(f"Method 3 failed: {e}")

    try:
        results['method4'] = test_method_4()
    except Exception as e:
        print(f"Method 4 failed: {e}")

    print("\n" + "=" * 80)
    print("Summary:")
    for method, result in results.items():
        print(f"  {method}: {result}")

    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
