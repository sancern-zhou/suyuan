"""
测试系统提示词改进后的效果
"""
import sys
import os

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agent.prompts.react_prompts import REACT_SYSTEM_PROMPT

print("="*80)
print("系统提示词检查")
print("="*80)

# 检查提示词中是否包含JSON格式要求
json_requirements = [
    "严格JSON格式要求",
    "英文双引号",
    "禁止使用中文引号",
    "特殊字符必须转义",
    "Windows路径",
    "字符串必须闭合"
]

print("\n检查JSON格式要求：")
for requirement in json_requirements:
    if requirement in REACT_SYSTEM_PROMPT:
        print(f"✅ {requirement}")
    else:
        print(f"❌ {requirement} - 未找到")

# 显示相关部分
print("\n" + "="*80)
print("输出格式部分（前500字符）")
print("="*80)

start_idx = REACT_SYSTEM_PROMPT.find("## 输出格式")
if start_idx != -1:
    format_section = REACT_SYSTEM_PROMPT[start_idx:start_idx+1500]
    print(format_section[:500])

print("\n" + "="*80)
print("总结")
print("="*80)
print(f"提示词总长度: {len(REACT_SYSTEM_PROMPT)} 字符")
print(f"包含JSON格式示例: {'✅ 是' if '```json' in REACT_SYSTEM_PROMPT else '❌ 否'}")
print(f"包含错误示例: {'✅ 是' if '错误示例' in REACT_SYSTEM_PROMPT else '❌ 否'}")
print(f"包含正确示例: {'✅ 是' if '正确示例' in REACT_SYSTEM_PROMPT else '❌ 否'}")
