"""
修复被 update_tools_for_file_path.py 破坏的文件

问题模式:
1. data_id 和 file_path 提取代码被插入到 logger 调用中间
2. try-except 结构被破坏
3. 重复的提取代码
"""
import re
from pathlib import Path

def fix_broken_logger_calls(content: str) -> str:
    """修复被破坏的 logger 调用"""

    # 模式1: data_id = data_ref["data_id"] 和 file_path = data_ref["file_path"] 在 logger 调用中间
    # 示例: logger.info(..., count=len(data
    #         data_id = data_ref["data_id"]
    #         file_path = data_ref["file_path"]), ...)

    # 查找并修复这种模式
    pattern1 = r'(logger\.(?:info|debug|warning|error)\([^)]*\n[^)]*)(\s+data_id = data_ref\["data_id"\]\n\s+file_path = data_ref\["file_path"\]\))\)([^)]*\n)'

    def replace_logger_call(match):
        before = match.group(1)
        extraction = match.group(2)
        after = match.group(3)

        # 移除 extraction 中多余的右括号
        extraction_clean = extraction.replace('),', ',')

        # 提取 data_id 和 file_path 到 logger 外面
        # 找到 logger 调用开始的位置
        indent_match = re.search(r'^(\s+)', before)
        if not indent_match:
            return match.group(0)

        indent = indent_match.group(1)

        # 构建: 先提取, 再调用 logger
        result = f"{extraction_clean}\n{indent}{before.rstrip()}\n{indent}{after.lstrip()}"
        return result

    content = re.sub(pattern1, replace_logger_call, content, flags=re.MULTILINE | re.DOTALL)

    return content


def fix_try_except_structure(content: str) -> str:
    """修复被破坏的 try-except 结构"""

    # 模式: except Exception as save_error: 后面直接跟了 data_id = data_ref...
    # 需要找到并移动这些代码

    lines = content.split('\n')
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检查是否是 except 行
        if re.match(r'\s+except Exception as \w+:', line):
            fixed_lines.append(line)
            i += 1

            # 检查下一行是否是 data_id = data_ref...
            if i < len(lines) and 'data_id = data_ref["data_id"]' in lines[i]:
                # 跳过这些行，它们应该在 try 块中
                while i < len(lines) and ('data_ref["data_id"]' in lines[i] or 'data_ref["file_path"]' in lines[i]):
                    i += 1
            continue

        fixed_lines.append(line)
        i += 1

    return '\n'.join(fixed_lines)


def fix_duplicate_extraction(content: str) -> str:
    """删除重复的 data_id/file_path 提取代码"""

    lines = content.split('\n')
    fixed_lines = []
    prev_extraction = None

    for line in lines:
        current_extraction = ('data_id = data_ref["data_id"]' in line or
                             'file_path = data_ref["file_path"]' in line)

        if current_extraction:
            # 检查是否和上一行相同
            if prev_extraction and line.strip() == fixed_lines[-1].strip():
                # 跳过重复行
                continue
            fixed_lines.append(line)
            prev_extraction = current_extraction
        else:
            fixed_lines.append(line)
            prev_extraction = False

    return '\n'.join(fixed_lines)


def fix_file(file_path: Path):
    """修复单个文件"""
    print(f"Fixing: {file_path.relative_to('backend')}")

    content = file_path.read_text(encoding='utf-8')
    original = content

    # 应用修复
    content = fix_duplicate_extraction(content)
    content = fix_broken_logger_calls(content)
    content = fix_try_except_structure(content)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"  [OK] Fixed")
        return True
    else:
        print(f"  [SKIP] No changes")
        return False


def main():
    """批量修复所有语法错误的文件"""
    broken_files = [
        'app/tools/query/get_carbon_data/tool.py',
        'app/tools/query/get_particulate_data/tool.py',
        'app/tools/query/get_satellite_data/tool.py',
        'app/tools/query/get_vocs_data/tool.py',
        'app/tools/query/get_weather_forecast/tool.py',
        'app/tools/analysis/calculate_vocs_pmf/tool.py',
        'app/tools/analysis/pybox_integration/tool.py',
        'app/tools/analysis/smart_chart_generator/tool.py',
        'app/tools/analysis/trajectory_source_analysis/tool.py',
    ]

    fixed_count = 0
    for file_path_str in broken_files:
        file_path = Path(f'backend/{file_path_str}')
        if file_path.exists():
            if fix_file(file_path):
                fixed_count += 1
        else:
            print(f"  [SKIP] File not found: {file_path_str}")

    print(f"\n[COMPLETE] Fixed {fixed_count} files")


if __name__ == "__main__":
    main()
