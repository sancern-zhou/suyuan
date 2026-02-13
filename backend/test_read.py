#!/usr/bin/env python
"""Quick test read_file"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test():
    from app.tools.utility.read_file_tool import ReadFileTool

    tool = ReadFileTool()
    result = await tool.execute(path='CLAUDE.md')

    print(f'Status: {result["status"]}')
    print(f'Success: {result["success"]}')
    print(f'Summary: {result.get("summary", "N/A")}')

    if result.get('success'):
        data = result['data']
        print(f'Type: {data["type"]}')
        print(f'Size: {data["size"]} bytes')
        print(f'Content length: {len(data["content"])} chars')
        print(f'Truncated: {"truncated" in data}')

        # Write full result to file
        with open('read_file_ok.txt', 'w', encoding='utf-8') as f:
            f.write(f"Status: {result['status']}\n")
            f.write(f"Success: {result['success']}\n")
            f.write(f"Summary: {result.get('summary', 'N/A')}\n\n")
            f.write(f"Content:\n{data['content']}")

        print("\nFull result written to: read_file_ok.txt")
    else:
        print(f'Error: {result.get("error")}')

asyncio.run(test())
