"""
UnpackOffice 工具 - 解包 Office 文件（DOCX/XLSX/PPTX → XML）

功能：
- 将 Office 文件（ZIP 格式）解包为 XML 文件
- 支持 DOCX、XLSX、PPTX 格式
- 自动创建输出目录
- 返回 XML 文件列表供后续编辑
- 自动生成PDF预览（仅Word和PowerPoint）

使用场景：
- 精确编辑 Office 文件内容（XML 级别）
- 批量修改文档结构
- 提取文档元数据
- 预览文档内容（PDF格式）
"""
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()

# PDF转换器导入（懒加载避免循环依赖）
def get_pdf_converter():
    try:
        from app.services.pdf_converter import pdf_converter
        return pdf_converter
    except ImportError:
        logger.warning("pdf_converter_not_available")
        return None


class UnpackOfficeTool(LLMTool):
    """
    Office 文件解包工具

    功能：
    - 将 Office 文件（DOCX/XLSX/PPTX）解包为 XML 文件
    - Office 文件本质是 ZIP 压缩的 XML 文件集合
    - 解包后可使用 read_file/edit_file 工具编辑 XML
    """

    def __init__(self):
        super().__init__(
            name="unpack_office",
            description="""解包 Office 文件到目录，提取 XML 文件用于编辑

功能：
- 将 DOCX/XLSX/PPTX 文件解包为 XML 文件
- 自动创建输出目录
- 返回 XML 文件列表供后续编辑

使用场景：
- 精确编辑 Office 文件（XML 级别控制）
- 批量修改文档结构
- 提取文档元数据

示例：
- unpack_office(path="report.docx", output_dir="unpacked/")
- unpack_office(path="data.xlsx", output_dir="temp/excel/")

参数说明：
- path: Office 文件路径（.docx/.xlsx/.pptx）
- output_dir: 输出目录路径（自动创建）

注意：
- 解包后使用 read_file/edit_file 编辑 XML
- 编辑完成后使用 pack_office 重新打包
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        # 使用项目根目录（动态适配实际部署路径）
        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        path: str,
        output_dir: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        解包 Office 文件

        Args:
            path: Office 文件路径（与 read_file 工具参数一致）
            output_dir: 输出目录路径（可选，默认在源文件目录创建 unpacked_* 目录）

        Returns:
            {
                "success": bool,
                "data": {
                    "output_dir": str,          # 输出目录相对路径
                    "file_count": int,           # 总文件数
                    "xml_files": list[str],      # XML 文件完整路径列表（相对于 working_dir）
                    "xml_count": int,            # XML 文件数量
                    "image_files": list[str],    # 图片文件完整路径列表（相对于 working_dir）
                    "image_count": int,          # 图片文件数量
                    "rels_files": list[str],     # 关系文件完整路径列表（相对于 working_dir）
                    "rels_count": int,           # 关系文件数量
                    "other_files": list[str],    # 其他文件完整路径列表（相对于 working_dir）
                    "other_count": int,          # 其他文件数量
                    "main_document": str         # 主文档路径
                },
                "summary": str
            }
        """
        try:
            # 1. 路径解析（简单处理，不过度工程化）
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.working_dir / file_path
            file_path = file_path.resolve()

            # 检查文件是否存在
            if not file_path.exists():
                return {
                    "success": False,
                    "data": {
                        "error": f"文件不存在: {file_path}",
                        "working_directory": str(self.working_dir),
                        "suggestion": f"请使用相对路径（如 '报告模板/file.docx'）或绝对路径"
                    },
                    "summary": f"文件不存在: {file_path.name}"
                }

            # 如果未指定输出目录，自动生成
            if output_dir is None:
                file_name = file_path.stem  # 不带扩展名的文件名
                output_dir = file_path.parent / f"unpacked_{file_name}"
            else:
                output_dir_path = Path(output_dir)
                if not output_dir_path.is_absolute():
                    output_dir_path = self.working_dir / output_dir_path
                output_dir = output_dir_path.resolve()

            # 2. 检查文件格式
            if file_path.suffix.lower() not in ['.docx', '.xlsx', '.pptx']:
                return {
                    "success": False,
                    "data": {"error": f"不支持的文件格式: {file_path.suffix}"},
                    "summary": "解包失败：格式不支持"
                }

            # 3. 创建输出目录
            output_dir.mkdir(parents=True, exist_ok=True)

            # 4. 解包 ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)

            # 5. 统计文件（按类型分类）
            all_files = list(output_dir.rglob("*"))
            file_count = sum(1 for f in all_files if f.is_file())

            # 分类文件（使用完整的相对路径，便于 LLM 直接使用）
            xml_files = []
            image_files = []
            rels_files = []
            other_files = []

            for f in all_files:
                if not f.is_file():
                    continue

                # 使用相对于 working_dir 的完整路径（LLM 可直接使用）
                try:
                    rel_path = str(f.relative_to(self.working_dir))
                    # 统一使用正斜杠（跨平台兼容）
                    rel_path = rel_path.replace("\\", "/")
                except ValueError:
                    # 如果不在 working_dir 下，使用绝对路径
                    rel_path = str(f.resolve()).replace("\\", "/")

                if f.suffix == '.xml':
                    xml_files.append(rel_path)
                elif f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']:
                    image_files.append(rel_path)
                elif f.suffix == '.rels':
                    rels_files.append(rel_path)
                else:
                    other_files.append(rel_path)

            logger.info(
                "unpack_office_success",
                file=str(file_path),
                output_dir=str(output_dir),
                file_count=file_count,
                xml_count=len(xml_files),
                image_count=len(image_files),
                rels_count=len(rels_files)
            )

            # 生成PDF预览（仅支持Word和PowerPoint）
            pdf_preview = None
            try:
                converter = get_pdf_converter()
                if converter and file_path.suffix.lower() in ['.docx', '.pptx']:
                    pdf_preview = await converter.convert_to_pdf(str(file_path))
                    logger.info(
                        "unpack_office_pdf_generated",
                        pdf_id=pdf_preview["pdf_id"],
                        pdf_url=pdf_preview["pdf_url"]
                    )
            except Exception as pdf_error:
                logger.warning("unpack_office_pdf_conversion_failed", error=str(pdf_error))

            # 返回相对路径（便于 LLM 后续操作）
            try:
                relative_output_dir = str(output_dir.relative_to(self.working_dir)).replace("\\", "/")
            except ValueError:
                # 如果不在 working_dir 下，返回绝对路径
                relative_output_dir = str(output_dir).replace("\\", "/")

            result_data = {
                "output_dir": relative_output_dir,  # 相对路径（统一使用正斜杠）
                "file_count": file_count,
                "source_file": str(file_path),  # 添加原始文件路径，方便PDF预览
                # 分类文件列表（完整路径，LLM 可直接使用）
                "xml_files": xml_files,
                "xml_count": len(xml_files),
                "image_files": image_files,
                "image_count": len(image_files),
                "rels_files": rels_files,
                "rels_count": len(rels_files),
                "other_files": other_files,
                "other_count": len(other_files),
                "main_document": f"{relative_output_dir}/word/document.xml"  # 主文档路径
            }

            # 如果有PDF预览，添加到数据中
            if pdf_preview:
                result_data["pdf_preview"] = pdf_preview

            return {
                "success": True,
                "data": result_data,
                "summary": f"已解包 {file_path.name} 到 {relative_output_dir}，共 {file_count} 个文件"
                          f"（{len(xml_files)} 个 XML，{len(image_files)} 个图片，{len(rels_files)} 个关系文件）"
            }

        except zipfile.BadZipFile:
            logger.error("unpack_office_bad_zip", file=file_path)
            return {
                "success": False,
                "data": {"error": "文件不是有效的 ZIP 格式"},
                "summary": "解包失败：文件损坏"
            }
        except Exception as e:
            logger.error("unpack_office_failed", file=file_path, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"解包失败：{str(e)[:80]}"
            }

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "unpack_office",
            "description": """解包 Office 文件到目录，提取 XML 文件用于编辑

将 DOCX/XLSX/PPTX 文件解包为 XML 文件，供后续精确编辑。

使用场景：
- 精确编辑 Office 文件（XML 级别控制）
- 批量修改文档结构
- 提取文档元数据

示例：
- unpack_office(path="report.docx")  # 自动创建 unpacked_report 目录（在源文件同目录）
- unpack_office(path="data.xlsx", output_dir="temp/")

解包后操作：
- read_file(path="unpacked_report/word/document.xml")  # 读取主文档
- edit_file(path="unpacked_report/word/document.xml", ...)  # 编辑文档
- pack_office(input_dir="unpacked_report", output_file="report_edited.docx")  # 重新打包

注意：
- 返回的 output_dir 是相对路径（便于后续工具使用）
- 主文档路径：{output_dir}/word/document.xml（DOCX）
- 输出目录默认在源文件同目录下（不是项目根目录）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Office 文件路径（.docx/.xlsx/.pptx）。示例：'report.docx' 或 'D:/work/data.xlsx'"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录路径（可选，相对路径）。默认在源文件目录创建 unpacked_<文件名> 目录。示例：'unpacked/' 或 'temp/excel/'"
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = UnpackOfficeTool()
