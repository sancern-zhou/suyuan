#!/usr/bin/env python
"""Test read_file with app/main.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test():
    from app.tools.utility.read_file_tool import ReadFileTool

    tool = ReadFileTool()
    result = await tool.execute(path='app/main.py')

    # Write to file to avoid encoding issues
    with open('test_read_result.txt', 'w', encoding='utf-8') as f:
        f.write('=== read_file Tool Test ===\n\n')
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
                f.write('RESULT: PASSED - Content is complete\n\n')

            # Show preview
            f.write('Content Preview (first 500 chars):\n')
            f.write('-' * 50 + '\n')
            f.write(data['content'][:500])
            f.write('\n' + '-' * 50 + '\n\n')

            # Verify full content
            original_file = Path('app/main.py')
            original_size = original_file.stat().st_size
            read_size = len(data['content'].encode('utf-8'))
            f.write(f'Original Size: {original_size} bytes\n')
            f.write(f'Read Size: {read_size} bytes\n')
            f.write(f'Match: {original_size == read_size}\n\n')

            if original_size == read_size:
                f.write('\n=== FINAL RESULT: PASSED ===\n')
                f.write('Full content read without truncation\n')
            else:
                f.write('\n=== FINAL RESULT: WARNING ===\n')
                f.write('Size mismatch (encoding issue?)\n')
        else:
            f.write(f'Error: {result.get("error")}\n\n')
            f.write('\n=== FINAL RESULT: FAILED ===\n')

    # Print to console
    with open('test_read_result.txt', 'r', encoding='utf-8') as f:
        content = f.read()
        # Find key lines
        for line in content.split('\n'):
            if any(keyword in line for keyword in ['RESULT:', 'FINAL RESULT:', 'Status:', 'Success:', 'Match:']):
                print(line)

asyncio.run(test())
