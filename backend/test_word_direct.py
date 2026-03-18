# -*- coding: utf-8 -*-
"""
Direct Word COM API test - no wrapper classes
"""

import sys
import os
import time


def main():
    print("=" * 80)
    print("Direct Word COM API Test")
    print("=" * 80)

    # Create Word application
    print("\n[1] Starting Word...")
    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    print(f"Word version: {word.Version}")

    # Create test document
    print("\n[2] Creating test document...")
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

    test_file = r"D:\溯源\backend\test_word_direct.docx"
    doc.SaveAs(test_file)
    print(f"Created: {test_file}")

    # Read original content
    print("\n[3] Reading original content...")
    original_text = doc.Content.Text
    print(f"Original (first 200 chars):\n{original_text[:200]}")

    search_text = "41微克/立方米"
    original_count = original_text.count(search_text)
    print(f"\nCount of '{search_text}': {original_count}")

    # Perform replacement
    print(f"\n[4] Performing replacement...")
    print(f"Search: '{search_text}' -> Replace: ''")

    find = doc.Content.Find
    find.ClearFormatting()
    find.Text = search_text
    find.Forward = True
    find.Wrap = 1  # wdFindContinue
    find.MatchCase = False
    find.MatchWholeWord = False

    # Execute replace all
    result = find.Execute(Replace=2)  # wdReplaceAll = 2

    print(f"\nReplace result:")
    print(f"  result: {result}")
    print(f"  type: {type(result).__name__}")

    # Check modified content (before saving)
    print("\n[5] Checking content BEFORE save...")
    modified_before_save = doc.Content.Text
    count_before_save = modified_before_save.count(search_text)
    print(f"  Count before save: {count_before_save}")
    print(f"  Content changed: {original_text != modified_before_save}")

    # Save document
    print("\n[6] Saving document...")
    try:
        doc.Save()
        print("  Save successful")
    except Exception as e:
        print(f"  Save failed: {e}")

    # Check modified content (after saving)
    print("\n[7] Checking content AFTER save...")
    modified_after_save = doc.Content.Text
    count_after_save = modified_after_save.count(search_text)
    print(f"  Count after save: {count_after_save}")

    # Close document
    print("\n[8] Closing document...")
    doc.Close(SaveChanges=0)  # Don't save again

    # Wait for file to be written
    print("\n[9] Waiting for file write...")
    time.sleep(3)

    # Reopen and verify
    print("\n[10] Reopening document to verify...")
    doc2 = word.Documents.Open(test_file)
    reopened_text = doc2.Content.Text
    reopened_count = reopened_text.count(search_text)
    print(f"  Count in reopened file: {reopened_count}")

    doc2.Close(SaveChanges=0)

    # Quit Word
    print("\n[11] Quitting Word...")
    word.Quit()

    # Wait for Word to fully exit
    time.sleep(2)

    # Analysis
    print("\n[12] Analysis...")
    print("=" * 80)

    print(f"Original count:    {original_count}")
    print(f"After replace:     {count_before_save}")
    print(f"After save:       {count_after_save}")
    print(f"Reopened file:    {reopened_count}")

    if reopened_count == 0:
        print("\nSUCCESS: All text was removed and saved!")
        success = True
    elif reopened_count < original_count:
        print(f"\nPARTIAL: {original_count - reopened_count}/{original_count} removed")
        success = False
    else:
        print("\nFAILED: File was NOT modified!")
        success = False

    # Cleanup
    print("\n[13] Cleanup...")
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
