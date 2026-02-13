"""
Simple test for read_file tool
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool


async def main():
    print("="*70)
    print("read_file Tool Test")
    print("="*70)

    tool = ReadFileTool()

    # Test 1: Read README.md
    print("\n[Test 1] Reading README.md")
    result = await tool.execute(path="README.md", encoding="utf-8")

    print(f"Status: {result['status']}")
    print(f"Success: {result['success']}")
    print(f"Summary: {result.get('summary', 'N/A')}")

    if result.get('success'):
        data = result['data']
        print(f"\nFile Info:")
        print(f"  Type: {data['type']}")
        print(f"  Format: {data['format']}")
        print(f"  Size: {data['size']} bytes")
        print(f"  Path: {data['path']}")

        content = data['content']
        print(f"\nContent Stats:")
        print(f"  Total chars: {len(content)}")
        print(f"  Total lines: {content.count(chr(10)) + 1}")

        # Check if truncated
        if 'truncated' in data:
            print(f"\n[WARNING] Content is truncated")
        else:
            print(f"\n[OK] Content is complete (not truncated)")

        # Show preview
        print(f"\nContent Preview (first 500 chars):")
        print("-" * 50)
        print(content[:500])
        print("-" * 50)

    # Test 2: Check tool schema
    print("\n" + "="*70)
    print("[Test 2] Tool Schema")
    print("="*70)

    schema = tool.get_function_schema()
    print(f"Tool Name: {schema['name']}")
    print(f"Description: {schema['description'][:100]}...")
    print(f"Required Params: {schema['parameters']['required']}")
    print(f"Optional Params: {list(schema['parameters']['properties'].keys())}")

    # Test 3: Check if auto_analyze parameter exists
    if 'auto_analyze' in schema['parameters']['properties']:
        print(f"\n[OK] auto_analyze parameter exists")
    else:
        print(f"\n[WARNING] auto_analyze parameter missing")

    if 'analysis_type' in schema['parameters']['properties']:
        print(f"[OK] analysis_type parameter exists")
    else:
        print(f"[WARNING] analysis_type parameter missing")

    print("\n" + "="*70)
    print("Test Complete")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
