"""
测试LLM响应解析器的Windows路径修复功能 v2
"""
import sys
import os
import json

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser

def test_real_world_case():
    """测试真实世界的失败案例"""
    parser = LLMResponseParser()

    # 这是从日志中提取的真实失败案例
    # 注意：这里的 D:\溯源 中的反斜杠是未转义的
    real_case = r'''{
  "thought": "用户需要在当前工作目录D:\溯源中搜索一个具体的Word文档文件"2025年臭氧垂直报告7-ok - 副本.docx"。这是一个文件搜索任务，需要使用bash工具来执行搜索命令。我将使用Windows的dir命令配合通配符来搜索该文件。",
  "reasoning": "用户明确要求搜索一个特定的Word文档文件。由于用户之前已经查看了当前工作目录结构，我需要在当前目录及其子目录中搜索该文件。我将使用dir命令配合通配符来搜索，这样可以递归搜索所有子目录。这是一个简单的文件搜索任务，不需要调用其他大气环境工具。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir /S /B *臭氧垂直*7-ok*副本*.docx",
      "timeout": 30000,
      "working_dir": "D:\\溯源"
    }
  }
}'''

    print("="*80)
    print("真实案例测试：包含未转义的Windows路径")
    print("="*80)

    # 首先验证这个JSON确实是无效的
    print("\n1. 验证原始JSON确实是无效的:")
    try:
        json.loads(real_case)
        print("⚠️ 原始JSON可以被解析（与预期不符）")
    except json.JSONDecodeError as e:
        print(f"✅ 原始JSON解析失败（符合预期）")
        print(f"   错误: {e}")

    # 测试预处理
    print("\n2. 测试预处理功能:")
    fixed = parser._preprocess_content(real_case)
    print(f"原始内容长度: {len(real_case)}")
    print(f"修复后长度: {len(fixed)}")
    print(f"内容是否变化: {fixed != real_case}")

    if fixed != real_case:
        print("✅ 预处理检测到问题并修复")
        # 尝试解析修复后的内容
        try:
            data = json.loads(fixed)
            print("✅ 修复后的JSON可以成功解析")
            print(f"   键: {list(data.keys())}")
        except json.JSONDecodeError as e:
            print(f"❌ 修复后的JSON仍然无法解析: {e}")
    else:
        print("⚠️ 预处理未检测到问题")

    # 显示部分内容用于调试
    print("\n3. 原始内容片段:")
    print(real_case[:300])

    # 测试完整解析
    print("\n4. 测试完整解析流程:")
    result = parser.parse(real_case)
    print(f"解析成功: {result['success']}")

    if result['success']:
        print("✅ 完整解析成功！")
        print(f"数据键: {list(result['data'].keys())}")
    else:
        print("❌ 完整解析失败")
        if result.get('error'):
            error_info = result['error']
            print(f"错误策略: {error_info.get('strategy')}")
            print(f"错误类型: {error_info.get('error_type')}")
            print(f"错误消息: {error_info.get('error_msg')}")

def test_simple_unescaped_path():
    """测试简单的未转义路径"""
    parser = LLMResponseParser()

    # 简单案例：只有路径有问题
    simple_case = r'''{"path": "D:\test\file.txt"}'''

    print("\n" + "="*80)
    print("简单案例：只有未转义的路径")
    print("="*80)

    print(f"\n原始内容: {simple_case}")

    # 验证确实是无效的
    try:
        json.loads(simple_case)
        print("⚠️ 原始JSON可以被解析")
    except json.JSONDecodeError as e:
        print(f"✅ 原始JSON解析失败: {e}")

    # 预处理
    fixed = parser._preprocess_content(simple_case)
    print(f"\n修复后内容: {fixed}")

    # 尝试解析
    try:
        data = json.loads(fixed)
        print(f"✅ 修复成功: {data}")
    except json.JSONDecodeError as e:
        print(f"❌ 修复失败: {e}")

def test_mixed_escaped_unescaped():
    """测试混合转义和未转义的情况"""
    parser = LLMResponseParser()

    # 混合案例：部分路径已转义，部分未转义
    mixed_case = r'''{"dir1": "D:\test", "dir2": "E:\\already\\escaped"}'''

    print("\n" + "="*80)
    print("混合案例：部分转义，部分未转义")
    print("="*80)

    print(f"\n原始内容: {mixed_case}")

    # 预处理
    fixed = parser._preprocess_content(mixed_case)
    print(f"修复后内容: {fixed}")

    # 解析
    try:
        data = json.loads(fixed)
        print(f"✅ 解析成功: {data}")
    except json.JSONDecodeError as e:
        print(f"❌ 解析失败: {e}")

if __name__ == "__main__":
    test_real_world_case()
    test_simple_unescaped_path()
    test_mixed_escaped_unescaped()

    print("\n" + "="*80)
    print("解析统计")
    print("="*80)
    parser = LLMResponseParser()  # 新实例获取完整统计
    stats = parser.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
