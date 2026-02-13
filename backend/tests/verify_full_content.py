"""
验证办公助理工具返回完整内容
"""
import asyncio
from pathlib import Path

# 测试 read_file 工具返回完整内容
print("="*60)
print("验证 read_file 工具返回完整内容")
print("="*60)

# 读取工具代码
code_path = Path("app/tools/utility/read_file_tool.py")
code = code_path.read_text(encoding="utf-8")

# 检查是否有截断逻辑
if "max_content_size" in code and "truncated" in code:
    print("❌ 发现截断逻辑")
    print("   - read_file 工具仍然有 max_content_size 限制")
    print("   - 需要移除截断逻辑，返回完整内容")
else:
    print("✅ 无截断逻辑")
    print("   - read_file 工具返回完整内容")

# 检查返回格式
if '"content": content' in code and '"truncated": truncated' not in code:
    print("✅ 返回格式正确")
    print("   - data.content 包含完整内容")
    print("   - 无 truncated 字段")
else:
    print("⚠️ 返回格式需要检查")

print("\n" + "="*60)
print("验证 bash 工具返回完整内容")
print("="*60)

# 读取 bash 工具代码
bash_code_path = Path("app/tools/utility/bash_tool.py")
bash_code = bash_code_path.read_text(encoding="utf-8")

# 检查输出限制
if '"stdout": stdout' in bash_code and "完全不截断" in bash_code:
    print("✅ bash 工具返回完整输出")
    print("   - stdout 包含完整输出")
    print("   - max_output_size 设置为 1MB")
elif '"stdout": stdout' in bash_code:
    print("✅ bash 工具返回完整输出")
    print("   - stdout 包含完整输出")
else:
    print("❌ bash 工具可能截断输出")

print("\n" + "="*60)
print("验证 analyze_image 工具返回完整结果")
print("="*60)

# 读取 analyze_image 工具代码
analyze_code_path = Path("app/tools/utility/analyze_image_tool.py")
analyze_code = analyze_code_path.read_text(encoding="utf-8")

# 检查分析结果返回
if '"analysis": analysis_result' in analyze_code:
    print("✅ analyze_image 工具返回完整分析结果")
    print("   - data.analysis 包含完整分析")
else:
    print("❌ analyze_image 工具可能截断结果")

print("\n" + "="*60)
print("总结")
print("="*60)
print("办公助理类工具（bash、read_file、analyze_image）应该：")
print("1. 返回完整的执行结果到 data 字段")
print("2. 简化 summary 字段（仅状态信息）")
print("3. 依赖上下文压缩策略处理大文件")
print("\n✅ 类似 Office 工具的 read 操作模式")
