#!/usr/bin/env python3
"""
技能索引生成脚本

自动扫描 backend/docs/skills/ 目录，生成 SKILLS_INDEX.md 索引文件。

功能：
1. 扫描技能目录下的所有 .md 文件
2. 解析每个文档的第一级标题（作为技能名称）
3. 提取概述段落（作为技能描述）
4. 生成 SKILLS_INDEX.md 文件

使用方式：
    python backend/scripts/generate_skills_index.py

集成到启动脚本：
    在 backend/start.sh 和 backend/start.bat 中添加调用
"""
from pathlib import Path
from datetime import datetime
import re


def parse_skill_file(file_path: Path) -> dict:
    """
    解析技能文件，提取信息

    Args:
        file_path: 技能文件路径

    Returns:
        {
            "name": str,           # 技能名称（从第一行H1标题提取）
            "description": str,    # 技能描述（从概述段落提取）
            "file": str,           # 相对文件路径
            "category": str        # 分类（从文件路径或内容推断）
        }
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split('\n')

        # 默认值
        name = file_path.stem
        description = "暂无描述"
        category = "其他"

        # 解析标题和描述
        in_code_block = False
        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 检测代码块开始/结束
            if line_stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            # 第一级标题（技能名称）- 跳过代码块
            if line_stripped.startswith("# ") and name == file_path.stem and not in_code_block:
                name = line_stripped[2:].strip()

            # 概述段落
            if line_stripped.startswith("## 概述") or line_stripped.startswith("概述："):
                # 尝试读取下一行作为描述
                if i + 1 < len(lines):
                    desc_line = lines[i + 1].strip()
                    # 跳过空行和标题
                    if desc_line and not desc_line.startswith("#"):
                        description = desc_line

            # 适用场景（用于分类）
            if line_stripped.startswith("## 适用场景"):
                # 根据场景内容推断分类
                context_lines = lines[i+1:min(i+10, len(lines))]
                context_text = "\n".join(context_lines).lower()

                if "excel" in context_text or "表格" in context_text:
                    category = "Excel处理"
                elif "可视化" in context_text or "图表" in context_text or "地图" in context_text:
                    category = "数据可视化"
                elif "文档" in context_text or "word" in context_text or "ppt" in context_text:
                    category = "文档处理"
                elif "数据分析" in context_text or "统计" in context_text:
                    category = "数据分析"

        return {
            "name": name,
            "description": description,
            "file": file_path.name,
            "category": category
        }

    except Exception as e:
        print(f"警告：解析文件失败 {file_path}: {e}")
        return {
            "name": file_path.stem,
            "description": "解析失败",
            "file": file_path.name,
            "category": "其他"
        }


def generate_index(skills_dir: Path) -> str:
    """
    生成技能索引内容

    Args:
        skills_dir: 技能目录路径

    Returns:
        索引文件内容（Markdown格式）
    """
    # 扫描所有 .md 文件
    md_files = [f for f in skills_dir.glob("*.md") if f.name != "SKILLS_INDEX.md"]

    if not md_files:
        return """# 技能索引

本文件由脚本自动生成，请勿手动编辑。

当前没有可用的技能文档。

---
生成时间：{timestamp}
技能总数：0
""".format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 解析所有技能文件
    skills = []
    for md_file in md_files:
        skill_info = parse_skill_file(md_file)
        skills.append(skill_info)

    # 按分类分组
    categories = {}
    for skill in skills:
        cat = skill["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(skill)

    # 生成索引内容
    lines = [
        "# 技能索引\n",
        "本文件由脚本自动生成，请勿手动编辑。\n",
        "\n"
    ]

    # 按分类输出
    for category, category_skills in sorted(categories.items()):
        lines.append(f"## {category}（{len(category_skills)}个技能）\n")
        lines.append("\n")

        for skill in sorted(category_skills, key=lambda x: x["name"]):
            # 格式: - [技能名称](文件路径.md) - 描述
            lines.append(f"- [{skill['name']}]({skill['file']}) - {skill['description']}\n")

        lines.append("\n")

    # 添加元数据
    lines.append("---\n")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"技能总数：{len(skills)}\n")

    return "".join(lines)


def main():
    """主函数"""
    # 确定技能目录路径
    script_dir = Path(__file__).parent
    skills_dir = script_dir.parent / "docs" / "skills"

    # 检查目录是否存在
    if not skills_dir.exists():
        print(f"错误：技能目录不存在: {skills_dir}")
        return 1

    print(f"扫描技能目录: {skills_dir}")

    # 生成索引内容
    index_content = generate_index(skills_dir)

    # 写入索引文件
    index_file = skills_dir / "SKILLS_INDEX.md"
    index_file.write_text(index_content, encoding="utf-8")

    print(f"✓ 索引文件已生成: {index_file}")

    # 统计信息
    md_files = [f for f in skills_dir.glob("*.md") if f.name != "SKILLS_INDEX.md"]
    print(f"✓ 扫描到 {len(md_files)} 个技能文档")

    return 0


if __name__ == "__main__":
    exit(main())
