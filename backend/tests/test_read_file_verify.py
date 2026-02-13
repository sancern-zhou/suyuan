"""
Verify read_file tool functionality
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool


async def verify_read_file():
    """Verify read_file tool"""
    print("="*70)
    print("read_file Tool Verification")
    print("="*70)

    tool = ReadFileTool()

    # Test reading README.md
    print("\n[Test] Reading README.md...")
    result = await tool.execute(path="README.md", encoding="utf-8")

    # Write results to file
    with open("read_file_test_result.txt", "w", encoding="utf-8") as f:
        f.write("read_file Tool Test Results\n")
        f.write("="*70 + "\n\n")

        f.write(f"Status: {result['status']}\n")
        f.write(f"Success: {result['success']}\n")
        f.write(f"Summary: {result.get('summary', 'N/A')}\n\n")

        if result.get('success'):
            data = result['data']
            f.write("File Info:\n")
            f.write(f"  Type: {data['type']}\n")
            f.write(f"  Format: {data['format']}\n")
            f.write(f"  Size: {data['size']} bytes\n")
            f.write(f"  Path: {data['path']}\n\n")

            content = data['content']
            f.write("Content Statistics:\n")
            f.write(f"  Total characters: {len(content)}\n")
            f.write(f"  Total lines: {content.count(chr(10)) + 1}\n\n")

            # Check if truncated
            if 'truncated' in data:
                f.write("RESULT: FAILED - Content is truncated\n")
            else:
                f.write("RESULT: PASSED - Content is complete (not truncated)\n")

            # Write content preview
            f.write("\nContent Preview (first 1000 chars):\n")
            f.write("-" * 70 + "\n")
            f.write(content[:1000])
            f.write("\n" + "-" * 70 + "\n")

            # Verify full content was read
            actual_file = Path("README.md")
            if actual_file.exists():
                original_size = actual_file.stat().st_size
                read_size = len(content.encode('utf-8'))
                f.write(f"\nFile Size Comparison:\n")
                f.write(f"  Original file size: {original_size} bytes\n")
                f.write(f"  Read content size: {read_size} bytes\n")
                f.write(f"  Match: {original_size == read_size}\n")

                if original_size == read_size:
                    f.write("\nFINAL RESULT: PASSED - Full content read without truncation\n")
                else:
                    f.write("\nFINAL RESULT: WARNING - Size mismatch (encoding issue?)\n")
        else:
            f.write(f"Error: {result.get('error', 'Unknown')}\n")
            f.write("\nFINAL RESULT: FAILED\n")

    # Print summary
    print("Results written to: read_file_test_result.txt")
    print("\nReading results...")
    with open("read_file_test_result.txt", "r", encoding="utf-8") as f:
        content = f.read()
        # Find the final result line
        for line in content.split('\n'):
            if 'FINAL RESULT' in line:
                print(f"  {line}")

    print("\n" + "="*70)
    print("Verification Complete")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(verify_read_file())
