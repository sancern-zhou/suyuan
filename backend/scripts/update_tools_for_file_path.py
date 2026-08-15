"""
批量更新工具以支持 file_path 返回

混合方案：让工具同时返回 data_id 和 file_path
"""

import re
from pathlib import Path

# 需要修改的模式
PATTERN_1 = r'data_id = context\.save_data\('
REPLACEMENT_1 = r'data_ref = context.save_data('

PATTERN_2 = r'\n\s+data_id = None\n'
REPLACEMENT_2 = r'\n        data_ref = None\n        file_path = None\n'

PATTERN_3 = r'data_id = context\.save_data\('
REPLACEMENT_3 = r'data_ref = context.save_data('


def update_tool_file(file_path: Path):
    """更新单个工具文件"""
    print(f"Processing: {file_path.name}")

    content = file_path.read_text(encoding="utf-8")
    original_content = content

    # 检查是否使用了 context.save_data
    if "context.save_data(" not in content:
        print(f"  [SKIP] No save_data found")
        return False

    # 修改1: 添加 data_ref 和 file_path 变量声明
    if re.search(r'data_id\s*=\s*None', content):
        content = re.sub(
            r'data_id\s*=\s*None',
            'data_ref = None\n        file_path = None',
            content
        )

    # 修改2: 替换 save_data 调用
    content = re.sub(
        r'data_id\s*=\s*context\.save_data\(',
        'data_ref = context.save_data(',
        content
    )

    # 检查是否有 data_id = data_ref["data_id"] 的解包
    if "data_ref = context.save_data(" in content:
        # 添加 data_id 和 file_path 解包
        content = re.sub(
            r'data_ref\s*=\s*context\.save_data\((.*?)\)\s*\n\s*([^)]+)',
            r'data_ref = context.save_data(\1)\n            \2\n            data_id = data_ref["data_id"]\n            file_path = data_ref["file_path"]',
            content,
            flags=re.MULTILINE | re.DOTALL
        )

    # 修改3: 更新 return 语句，添加 file_path
    # 查找包含 data_id 的 return 语句
    return_pattern = r'(return\s*{[^}]*"data_id":\s*data_id,)([^}]+\})'

    def add_file_path_to_return(match):
        ret_start = match.group(1)
        ret_body = match.group(2)

        # 在 data_id 后面插入 file_path
        modified = ret_start + '\n            "file_path": file_path,' + ret_body

        # 更新 summary
        modified = re.sub(
            r'(summary:.*?已保存为\s+)([^"]+)',
            r'\1\2（路径: {file_path}）',
            modified
        )

        return modified

    content = re.sub(return_pattern, add_file_path_to_return, content, flags=re.DOTALL)

    if content != original_content:
        file_path.write_text(content, encoding="utf-8")
        print(f"  [OK] Updated")
        return True
    else:
        print(f"  [SKIP] No changes needed")
        return False


def main():
    """批量更新所有工具"""
    tools_dir = Path("D:/溯源/backend/app/tools")

    # 查找所有工具文件
    tool_files = []
    for pattern in ["query/**/*.py", "analysis/**/*.py"]:
        tool_files.extend(tools_dir.glob(pattern))

    print(f"Found {len(tool_files)} tool files")

    updated_count = 0
    for tool_file in tool_files:
        if update_tool_file(tool_file):
            updated_count += 1

    print(f"\n[COMPLETE] Updated {updated_count} tool files")


if __name__ == "__main__":
    main()
