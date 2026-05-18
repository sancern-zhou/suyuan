"""
Agent 读取 .doc 文档示例

Agent 可以通过以下两步读取 .doc 格式文档：
1. 使用 bash 工具调用 LibreOffice 转换为 .docx
2. 使用 read_file 或 unpack_office 读取内容
"""

import subprocess
import os
from pathlib import Path

def convert_doc_to_docx(doc_path: str, output_dir: str = "/tmp") -> str:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        doc_path: .doc 文件路径
        output_dir: 输出目录

    Returns:
        转换后的 .docx 文件路径
    """
    doc_path = Path(doc_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用 LibreOffice 转换
    cmd = [
        "soffice",
        "--headless",
        "--convert-to", "docx",
        "--outdir", str(output_dir),
        str(doc_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise RuntimeError(f"转换失败: {result.stderr}")

    # 返回转换后的文件路径
    docx_path = output_dir / f"{doc_path.stem}.docx"
    return str(docx_path)


def convert_doc_to_text(doc_path: str, output_dir: str = "/tmp") -> str:
    """
    将 .doc 文件转换为纯文本格式

    Args:
        doc_path: .doc 文件路径
        output_dir: 输出目录

    Returns:
        转换后的 .txt 文件路径
    """
    doc_path = Path(doc_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用 LibreOffice 转换为文本
    cmd = [
        "soffice",
        "--headless",
        "--convert-to", "txt:Text (encoded)",
        "--outdir", str(output_dir),
        str(doc_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise RuntimeError(f"转换失败: {result.stderr}")

    # 返回转换后的文件路径
    txt_path = output_dir / f"{doc_path.stem}.txt"
    return str(txt_path)


# ============================================================================
# Agent 工作流程示例（伪代码）
# ============================================================================

"""
# Agent 可以这样读取 .doc 文件：

# Step 1: 调用 bash 工具转换
bash_result = await call_tool("bash", {
    "command": "soffice --headless --convert-to docx --outdir /tmp /path/to/file.doc"
})

# Step 2: 使用 read_file 读取转换后的文件
content = await call_tool("read_file", {
    "file_path": "/tmp/file.docx"
})

# 或者直接转换为文本更简单
bash_result = await call_tool("bash", {
    "command": "soffice --headless --convert-to txt --outdir /tmp /path/to/file.doc"
})

content = await call_tool("read_file", {
    "file_path": "/tmp/file.txt"
})
"""

if __name__ == "__main__":
    # 测试转换功能
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python doc_reader_example.py <doc文件路径>")
        sys.exit(1)

    doc_file = sys.argv[1]

    if not Path(doc_file).exists():
        print(f"错误: 文件不存在: {doc_file}")
        sys.exit(1)

    try:
        print(f"正在转换: {doc_file}")
        docx_path = convert_doc_to_docx(doc_file)
        print(f"转换成功: {docx_path}")

        # 也可以转换为纯文本
        txt_path = convert_doc_to_text(doc_file)
        print(f"文本版本: {txt_path}")

    except Exception as e:
        print(f"转换失败: {e}")
        sys.exit(1)
