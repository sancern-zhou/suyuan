#!/usr/bin/env python3
import os
import sys

# 切换到脚本目录
os.chdir('D:/溯源/backend')

# 添加路径
sys.path.insert(0, 'D:/溯源/backend/app')

# 执行分析
try:
    from analyze_tool_schemas import main
    main()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
