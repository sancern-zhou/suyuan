"""
PackOffice 工具 - 打包 XML 文件为 Office 文件（XML → DOCX/XLSX/PPTX）

功能：
- 将编辑后的 XML 文件打包为 Office 文件
- 支持 DOCX、XLSX、PPTX 格式
- 保持原始文件结构和压缩格式
- 自动备份原文件
- 自动生成PDF预览（仅Word和PowerPoint）

使用场景：
- 将编辑后的 XML 重新打包为 Office 文件
- 批量生成 Office 文档
- 自动化文档处理流程
"""
import zipfile
import shutil
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


class PackOfficeTool(LLMTool):
    """
    Office 文件打包工具

    功能：
    - 将 XML 文件目录打包为 Office 文件（DOCX/XLSX/PPTX）
    - 保持原始文件结构和压缩格式
    - 自动备份原文件（可选）
    """

    def __init__(self):
        super().__init__(
            name="pack_office",
            description="""打包 XML 目录为 Office 文件

功能：
- 将编辑后的 XML 文件打包为 DOCX/XLSX/PPTX
- 保持原始文件结构和压缩格式
- 自动备份原文件（可选）

使用场景：
- 将编辑后的 XML 重新打包为 Office 文件
- 批量生成 Office 文档
- 自动化文档处理流程

示例：
- pack_office(input_dir="unpacked/", output_file="report_edited.docx")
- pack_office(input_dir="temp/excel/", output_file="data.xlsx", backup=True)

参数说明：
- input_dir: XML 文件目录（unpack_office 的输出目录）
- output_file: 输出 Office 文件路径（.docx/.xlsx/.pptx）
- backup: 是否备份原文件（默认 False）

注意：
- 必须先使用 unpack_office 解包
- 使用 read_file/edit_file 编辑 XML 后再打包
- 打包前确保 XML 格式正确
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        input_dir: str,
        output_file: str,
        backup: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        打包 XML 目录为 Office 文件

        Args:
            input_dir: XML 文件目录
            output_file: 输出 Office 文件路径
            backup: 是否备份原文件

        Returns:
            {
                "success": bool,
                "data": {
                    "output_file": str,
                    "file_count": int,
                    "backup_file": str (可选)
                },
                "summary": str
            }
        """
        try:
            # 1. 路径解析
            input_dir = self._resolve_path(input_dir)
            output_file = self._resolve_path(output_file)

            if not input_dir or not output_file:
                return {
                    "success": False,
                    "data": {"error": "路径无效"},
                    "summary": "打包失败：路径无效"
                }

            if not input_dir.exists() or not input_dir.is_dir():
                return {
                    "success": False,
                    "data": {"error": f"输入目录不存在: {input_dir}"},
                    "summary": "打包失败：目录不存在"
                }

            # 2. 检查输出文件格式
            if output_file.suffix.lower() not in ['.docx', '.xlsx', '.pptx']:
                return {
                    "success": False,
                    "data": {"error": f"不支持的文件格式: {output_file.suffix}"},
                    "summary": "打包失败：格式不支持"
                }

            # 3. 备份原文件（如果存在且需要备份）
            backup_file = None
            if backup and output_file.exists():
                backup_file = output_file.with_suffix(output_file.suffix + '.bak')
                shutil.copy2(output_file, backup_file)
                logger.info("pack_office_backup", original=str(output_file), backup=str(backup_file))

            # 4. 创建输出目录（如果不存在）
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # 5. 打包为 ZIP（Office 格式）
            file_count = 0
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for file_path in input_dir.rglob("*"):
                    if file_path.is_file():
                        # 计算相对路径（保持目录结构）
                        arcname = file_path.relative_to(input_dir)
                        zip_ref.write(file_path, arcname)
                        file_count += 1

            # 6. 验证打包结果
            if not output_file.exists() or output_file.stat().st_size == 0:
                return {
                    "success": False,
                    "data": {"error": "打包后文件为空"},
                    "summary": "打包失败：文件为空"
                }

            logger.info(
                "pack_office_success",
                input_dir=str(input_dir),
                output_file=str(output_file),
                file_count=file_count,
                size=output_file.stat().st_size
            )

            # 获取API基础URL（从配置读取）
            from config.settings import settings
            api_base = settings.backend_host.rstrip("/")

            result_data = {
                "file_path": str(output_file),  # 统一使用 file_path 字段名（前端期望）
                "output_file": str(output_file),  # 保留向后兼容
                "file_count": file_count,
                "size": output_file.stat().st_size,
                "file_name": output_file.name
            }

            if backup_file:
                result_data["backup_file"] = str(backup_file)

            # 添加Word/Excel/PowerPoint文档下载链接
            from urllib.parse import quote
            encoded_path = quote(str(output_file))
            result_data["doc_url"] = f"{api_base}/api/utility/file/{encoded_path}"
            result_data["doc_download_filename"] = output_file.name

            # 生成PDF预览（仅支持Word和PowerPoint）
            try:
                converter = get_pdf_converter()
                if converter and output_file.suffix.lower() in ['.docx', '.pptx']:
                    pdf_preview = await converter.convert_to_pdf(str(output_file))
                    result_data["pdf_preview"] = pdf_preview
                    logger.info(
                        "pack_office_pdf_generated",
                        pdf_id=pdf_preview["pdf_id"],
                        pdf_url=pdf_preview["pdf_url"]
                    )
            except Exception as pdf_error:
                logger.warning("pack_office_pdf_conversion_failed", error=str(pdf_error))

            return {
                "success": True,
                "data": result_data,
                "summary": (
                    f"已打包 {file_count} 个文件为 {output_file.name}"
                    f"{f'（已备份原文件）' if backup_file else ''}"
                )
            }

        except zipfile.BadZipFile as e:
            logger.error("pack_office_bad_zip", input_dir=input_dir, error=str(e))
            return {
                "success": False,
                "data": {"error": "打包失败：ZIP 格式错误"},
                "summary": "打包失败：ZIP 格式错误"
            }
        except PermissionError as e:
            logger.error("pack_office_permission_denied", output_file=output_file, error=str(e))
            return {
                "success": False,
                "data": {"error": "打包失败：文件被占用或无权限"},
                "summary": "打包失败：文件被占用"
            }
        except Exception as e:
            logger.error("pack_office_failed", input_dir=input_dir, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"打包失败：{str(e)[:80]}"
            }

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析路径（支持相对路径和绝对路径）"""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            return file_path.resolve()

        except Exception as e:
            logger.error("pack_office_path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "pack_office",
            "description": "将unpack_office输出的XML目录重新打包为DOCX/XLSX/PPTX；打包前确保XML格式正确。",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_dir": {
                        "type": "string",
                        "description": "XML目录，通常为unpack_office的output_dir"
                    },
                    "output_file": {
                        "type": "string",
                        "description": "输出Office文件路径（docx/xlsx/pptx）"
                    },
                    "backup": {
                        "type": "boolean",
                        "description": "是否备份原文件（默认 False）",
                        "default": False
                    }
                },
                "required": ["input_dir", "output_file"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = PackOfficeTool()
