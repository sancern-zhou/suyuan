"""
特殊工具格式化器

处理特殊工具的结果格式化，如bash、Office工具、read_data_registry等。
"""

from typing import Dict, Any, List
import json

from .base import ObservationFormatter


class BashFormatter(ObservationFormatter):
    """Bash命令执行工具格式化器（bash）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        # bash工具通过stdout/stderr字段识别
        return "stdout" in data or "stderr" in data

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "stdout" in data and data["stdout"]:
            # 完整输出，不截断
            lines.append(f"**命令输出**:\n{data['stdout']}")

        if "stderr" in data and data["stderr"]:
            lines.append(f"**错误输出**:\n{data['stderr']}")

        if "exit_code" in data:
            lines.append(f"**退出码**: {data['exit_code']}")

        if "command" in data:
            lines.append(f"**执行命令**: {data['command']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 5  # 高优先级（bash工具很常用）


class OfficeFormatter(ObservationFormatter):
    """Office文档处理工具格式化器（Word/Excel/PPT）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        office_generators = [
            "word_edit", "find_replace_word", "accept_word_changes",
            "unpack_office", "pack_office", "recalc_excel", "add_ppt_slide",
            "read_docx", "read_xlsx", "read_pptx"
        ]
        return generator in office_generators

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []

        if "content" in data:
            lines.append(f"**文档内容**:\n```\n{data['content']}\n```")
        elif "images" in data:
            # extract_images 操作：显示完整图片列表
            images = data["images"]
            if isinstance(images, list):
                # extract_images 返回的图片列表
                lines.append(f"**提取的图片数量**: {len(images)}")
                for img in images:
                    lines.append(f"\n**图片 {img['index']}**:")
                    lines.append(f"  路径: `{img['path']}`")
                    lines.append(f"  尺寸: {img['width']} x {img['height']}")
            elif isinstance(images, int):
                # stats 操作返回的图片数量
                lines.append(f"**图片数量**: {images}")
        elif "tables" in data:
            # 表格数据（完整显示）
            tables = data["tables"]
            lines.append(f"**表格数量**: {data.get('table_count', len(tables))}")
            for idx, table in enumerate(tables):
                lines.append(f"\n**表格 {idx + 1}**: {table['rows']}行 × {table['cols']}列")
                lines.append(f"```json\n{json.dumps(table['data'], ensure_ascii=False, indent=2)}\n```")
        elif "data" in data and isinstance(data.get("data"), list):
            # Excel 数据（二维数组）
            lines.append(f"**数据内容**:\n```json\n{json.dumps(data['data'], ensure_ascii=False, indent=2)}\n```")

        # 显示统计信息
        if "stats" in data:
            lines.append(f"**统计信息**: {data['stats']}")

        # 显示范围信息（如果有）
        if "range" in data:
            lines.append(f"**读取范围**: 第{data['range']['start']+1}-{data['range']['end']}段（共{data['range']['total']}段）")
            if data.get("has_more"):
                lines.append(f"⚠️ 还有{data['range']['total']-data['range']['end']}段未读取，可继续分页读取")

        # 显示图片提示（read_docx 工具）
        if "has_images" in data and data["has_images"]:
            if "image_note" in data:
                lines.append(f"\n**图片信息**: {data['image_note']}")
            if "image_suggestion" in data:
                lines.append(f"**提取建议**: {data['image_suggestion']}")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 6


class ReadDataRegistryFormatter(ObservationFormatter):
    """数据注册表读取工具格式化器（read_data_registry）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "read_data_registry"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []
        # 显示完整的 data 字段内容（JSON 格式）
        lines.append(f"**完整结果**:")
        lines.append(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2, default=str)}\n```")
        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 7


class ParsePDFFormatter(ObservationFormatter):
    """PDF解析工具格式化器（parse_pdf）"""

    @classmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        return generator == "parse_pdf"

    @classmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        lines = []
        pdf_type = data.get("type", "")
        file_name = data.get("file_name", "")

        if pdf_type == "pdf_text":
            # 文本提取结果
            lines.append(f"**文件**: {file_name}")
            if "total_pages" in data:
                lines.append(f"**总页数**: {data['total_pages']}")
            if "pages_processed" in data:
                lines.append(f"**处理页数**: {data['pages_processed']}")
            if "content_length" in data:
                lines.append(f"**内容长度**: {data['content_length']} 字符")

            # 显示内容预览
            if "preview" in data:
                lines.append(f"\n**内容预览**:")
                lines.append(data["preview"])
            elif "content" in data:
                # 如果没有preview，截断显示
                content = data["content"]
                preview_length = 5000
                if len(content) > preview_length:
                    lines.append(f"\n**内容预览** (前{preview_length}字符):")
                    lines.append(content[:preview_length])
                    lines.append(f"\n... (还有 {len(content) - preview_length} 字符)")
                else:
                    lines.append(f"\n**内容**:")
                    lines.append(content)

            # 显示表格信息
            if "table_count" in data and data["table_count"] > 0:
                lines.append(f"\n**表格数量**: {data['table_count']}")

            # 显示图片信息
            if "image_count" in data and data["image_count"] > 0:
                lines.append(f"**图片数量**: {data['image_count']}")

            # 显示保存的文件路径
            if "result_file_path" in data:
                lines.append(f"\n**结果已保存**: `{data['result_file_path']}`")

        elif pdf_type == "pdf_ocr":
            # OCR识别结果
            lines.append(f"**文件**: {file_name}")
            lines.append(f"**OCR引擎**: {data.get('ocr_engine', 'unknown')}")
            if "pages_processed" in data:
                lines.append(f"**处理页数**: {data['pages_processed']}")
            if "content_length" in data:
                lines.append(f"**内容长度**: {data['content_length']} 字符")

            # 显示内容预览
            if "preview" in data:
                lines.append(f"\n**OCR识别结果预览**:")
                lines.append(data["preview"])
            elif "content" in data:
                # 如果没有preview，截断显示
                content = data["content"]
                preview_length = 5000
                if len(content) > preview_length:
                    lines.append(f"\n**OCR识别结果预览** (前{preview_length}字符):")
                    lines.append(content[:preview_length])
                    lines.append(f"\n... (还有 {len(content) - preview_length} 字符)")
                else:
                    lines.append(f"\n**OCR识别结果**:")
                    lines.append(content)

            # 显示保存的文件路径
            if "result_file_path" in data:
                lines.append(f"\n**结果已保存**: `{data['result_file_path']}`")

        elif pdf_type == "pdf_tables":
            # 表格提取结果
            lines.append(f"**文件**: {file_name}")
            table_count = data.get("table_count", 0)
            lines.append(f"**表格数量**: {table_count}")

            if table_count > 0 and "tables" in data:
                lines.append(f"\n**表格详情**:")
                for idx, table in enumerate(data["tables"][:5]):  # 最多显示5个表格
                    lines.append(f"\n表格 {idx + 1}: {table['rows']}行 × {table['cols']}列")
                    # 显示前3行数据作为预览
                    if "data" in table and len(table["data"]) > 0:
                        preview_rows = table["data"][:3]
                        lines.append(f"```json\n{json.dumps(preview_rows, ensure_ascii=False, indent=2)}\n```")
                if table_count > 5:
                    lines.append(f"\n... 还有 {table_count - 5} 个表格")

            # 显示保存的文件路径
            if "result_file_path" in data:
                lines.append(f"\n**结果已保存**: `{data['result_file_path']}`")

        elif pdf_type == "pdf_images":
            # 图片信息提取结果
            lines.append(f"**文件**: {file_name}")
            image_count = data.get("image_count", 0)
            lines.append(f"**图片数量**: {image_count}")

            if image_count > 0 and "images" in data:
                lines.append(f"\n**图片列表** (前10个):")
                for idx, img in enumerate(data["images"][:10]):
                    lines.append(f"{idx + 1}. 页码{img['page']}: {img.get('width', 0)}×{img.get('height', 0)}")
                if image_count > 10:
                    lines.append(f"\n... 还有 {image_count - 10} 个图片")

            # 显示保存的文件路径
            if "result_file_path" in data:
                lines.append(f"\n**结果已保存**: `{data['result_file_path']}`")

        elif pdf_type == "pdf_metadata":
            # 元数据提取结果
            lines.append(f"**文件**: {file_name}")
            lines.append(f"**页数**: {data.get('page_count', 'N/A')}")
            lines.append(f"**是否加密**: {'是' if data.get('is_encrypted') else '否'}")

            # 显示PDF元数据
            if "title" in data and data["title"]:
                lines.append(f"**标题**: {data['title']}")
            if "author" in data and data["author"]:
                lines.append(f"**作者**: {data['author']}")
            if "creator" in data and data["creator"]:
                lines.append(f"**创建工具**: {data['creator']}")
            if "creation_date" in data and data["creation_date"]:
                lines.append(f"**创建日期**: {data['creation_date']}")

            # 显示保存的文件路径
            if "result_file_path" in data:
                lines.append(f"\n**结果已保存**: `{data['result_file_path']}`")

        return lines

    @classmethod
    def get_priority(cls) -> int:
        return 8
