#!/usr/bin/env python
"""Test read_file with absolute path"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test():
    from app.tools.utility.read_file_tool import ReadFileTool

    tool = ReadFileTool()

    # Use absolute path
    test_file = Path(__file__).parent / 'app' / 'main.py'
    abs_path = str(test_file.resolve())

    print(f"Testing with absolute path: {abs_path}")

    result = await tool.execute(path=abs_path)

    # Write to file
    with open('test_read_result.txt', 'w', encoding='utf-8') as f:
        f.write('=== read_file Tool Test ===\n\n')
        f.write(f'Test File: {abs_path}\n')
        f.write(f'Status: {result["status"]}\n')
        f.write(f'Success: {result["success"]}\n')
        f.write(f'Summary: {result.get("summary", "N/A")}\n\n')

        if result.get('success'):
            data = result['data']
            f.write(f'File Type: {data["type"]}\n')
            f.write(f'Format: {data["format"]}\n')
            f.write(f'Size: {data["size"]} bytes\n')
            f.write(f'Content Length: {len(data["content"])} chars\n\n')

            # Check if truncated
            if 'truncated' in data:
                f.write('RESULT: FAILED - Content is truncated\n')
            else:
                f.write('RESULT: PASSED - Content is complete (not truncated)\n\n')

            # Verify full content
            original_size = test_file.stat().st_size
            read_size = len(data['content'].encode('utf-8'))
            f.write(f'Original Size: {original_size} bytes\n')
            f.write(f'Read Size: {read_size} bytes\n')
            f.write(f'Match: {original_size == read_size}\n\n')

            if original_size == read_size:
                f.write('\n=== FINAL RESULT: PASSED ===\n')
                f.write('Full content read without truncation\n')
                print('SUCCESS: read_file tool works correctly!')
            else:
                f.write('\n=== FINAL RESULT: WARNING ===\n')
                f.write(f'Size mismatch: {original_size} != {read_size}\n')
                print(f'WARNING: Size mismatch')
        else:
            f.write(f'Error: {result.get("error")}\n\n')
            f.write('\n=== FINAL RESULT: FAILED ===\n')
            print(f'FAILED: {result.get("error")}')

    print('\nFull results written to: test_read_result.txt')

asyncio.run(test())
