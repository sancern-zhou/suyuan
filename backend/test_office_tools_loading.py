#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 Office 工具是否正确加载"""

from app.agent import create_react_agent

# 创建 Agent
agent = create_react_agent()

# 获取所有工具
tools = list(agent.executor.tool_registry.keys())

# 查找 Office 工具
office_tools = [
    'unpack_office',
    'pack_office',
    'accept_word_changes',
    'find_replace_word',
    'recalc_excel',
    'add_ppt_slide'
]

print(f"Total tools: {len(tools)}")
print(f"\nOffice tools check:")
for tool in office_tools:
    status = "OK" if tool in tools else "MISSING"
    print(f"  [{status}] {tool}")

print(f"\nAll Office related tools:")
office_related = [t for t in tools if any(x in t for x in ['office', 'pack', 'word', 'excel', 'ppt', 'slide'])]
for tool in sorted(office_related):
    print(f"  - {tool}")

