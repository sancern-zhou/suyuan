"""
PowerPoint Win32 COM 工具

提供 PowerPoint 演示文稿的自动化处理能力：
- 读取幻灯片内容
- 添加/修改幻灯片
- 提取文本和形状
- 操作图表和表格
"""

import os
from typing import Dict, Any, List, Optional
import structlog

from .base_win32 import Win32Base

logger = structlog.get_logger()


class PPTWin32Tool(Win32Base):
    """
    PowerPoint 自动化工具

    支持的操作：
    - 读取幻灯片内容
    - 添加/修改幻灯片
    - 提取文本
    - 操作形状和文本框
    """

    def __init__(self, visible: bool = False):
        """
        初始化 PowerPoint 工具

        Args:
            visible: 是否显示 PowerPoint 窗口
        """
        super().__init__(
            app_name=self.APP_POWERPOINT,
            visible=visible,
            display_alerts=False
        )

    def open_presentation(self, file_path: str, read_only: bool = True):
        """
        打开 PowerPoint 演示文稿

        Args:
            file_path: 演示文稿路径
            read_only: 是否以只读方式打开

        Returns:
            Presentation 对象
        """
        try:
            self.ensure_initialized()

            abs_path = self.get_absolute_path(file_path)

            if not self.check_file_exists(abs_path):
                return None

            # 打开演示文稿
            presentation = self.app.Presentations.Open(
                FileName=abs_path,
                ReadOnly=read_only,
                Untitled=False,
                WithWindow=self.visible
            )

            logger.info(
                "ppt_presentation_opened",
                path=file_path,
                read_only=read_only
            )

            return presentation

        except Exception as e:
            logger.error(
                "ppt_open_failed",
                path=file_path,
                error=str(e)
            )
            return None

    def save_presentation(self, presentation, file_path: str):
        """
        保存 PowerPoint 演示文稿

        Args:
            presentation: Presentation 对象
            file_path: 保存路径
        """
        try:
            abs_path = self.get_absolute_path(file_path)

            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # 保存演示文稿
            presentation.SaveAs(abs_path)

            logger.info(
                "ppt_presentation_saved",
                path=file_path
            )

            return True

        except Exception as e:
            logger.error(
                "ppt_save_failed",
                path=file_path,
                error=str(e)
            )
            return False

    def close_presentation(self, presentation):
        """
        关闭 PowerPoint 演示文稿

        Args:
            presentation: Presentation 对象
        """
        try:
            presentation.Close()
            logger.debug("ppt_presentation_closed")
        except Exception as e:
            logger.warning("ppt_close_warning", error=str(e))

    def read_all_text(self, file_path: str) -> Dict[str, Any]:
        """
        读取 PowerPoint 演示文稿的所有文本

        Args:
            file_path: 演示文稿路径

        Returns:
            {
                "status": "success" | "failed",
                "slides": [
                    {
                        "index": 0,
                        "title": "幻灯片标题",
                        "content": ["文本1", "文本2", ...]
                    },
                    ...
                ],
                "slide_count": 幻灯片数量
            }
        """
        try:
            presentation = self.open_presentation(file_path, read_only=True)

            if not presentation:
                return {
                    "status": "failed",
                    "error": "无法打开演示文稿"
                }

            slides = []

            # 读取所有幻灯片
            for i, slide in enumerate(presentation.Slides):
                slide_data = {
                    "index": i + 1,
                    "title": "",
                    "content": []
                }

                # 遍历幻灯片中的所有形状
                for shape in slide.Shapes:
                    # 检查是否有文本框
                    if shape.HasTextFrame:
                        text_frame = shape.TextFrame
                        if text_frame.HasText:
                            text = text_frame.TextRange.Text.strip()

                            # 判断是否为标题（通常标题在第一个形状）
                            if not slide_data["title"]:
                                slide_data["title"] = text
                            else:
                                slide_data["content"].append(text)

                slides.append(slide_data)

            # 关闭演示文稿
            self.close_presentation(presentation)

            return {
                "status": "success",
                "slides": slides,
                "slide_count": len(slides),
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "ppt_read_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def replace_text(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        替换 PowerPoint 演示文稿中的文本

        Args:
            file_path: 演示文稿路径
            old_text: 要查找的文本
            new_text: 替换的文本
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "replacements": 替换次数,
                "output_file": "输出文件路径"
            }
        """
        try:
            presentation = self.open_presentation(file_path, read_only=False)

            if not presentation:
                return {
                    "status": "failed",
                    "error": "无法打开演示文稿"
                }

            replacements = 0

            # 遍历所有幻灯片
            for slide in presentation.Slides:
                # 遍历所有形状
                for shape in slide.Shapes:
                    # 检查是否有文本框
                    if shape.HasTextFrame:
                        text_frame = shape.TextFrame
                        if text_frame.HasText:
                            # 替换文本
                            text_range = text_frame.TextRange
                            if old_text in text_range.Text:
                                text_range.Replace(
                                    FindWhat=old_text,
                                    ReplaceWhat=new_text
                                )
                                replacements += 1

            # 保存演示文稿
            output_file = save_as or file_path
            self.save_presentation(presentation, output_file)

            # 关闭演示文稿
            self.close_presentation(presentation)

            return {
                "status": "success",
                "replacements": replacements,
                "output_file": output_file,
                "summary": "替换成功"
            }

        except Exception as e:
            logger.error(
                "ppt_replace_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def search_and_replace(
        self,
        file_path: str,
        search_text: str,
        replace_text: str = "",
        match_case: bool = False,
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        搜索并替换 PowerPoint 演示文稿中的文本

        Args:
            file_path: 演示文稿路径
            search_text: 要查找的文本
            replace_text: 替换的文本（默认为空，即删除）
            match_case: 是否区分大小写
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "replacements": 替换次数,
                "matches": ["匹配到的文本列表"],
                "output_file": "输出文件路径"
            }
        """
        try:
            presentation = self.open_presentation(file_path, read_only=False)

            if not presentation:
                return {
                    "status": "failed",
                    "error": "无法打开演示文稿"
                }

            replacements = 0
            matches = []

            # 遍历所有幻灯片
            for slide in presentation.Slides:
                # 遍历所有形状
                for shape in slide.Shapes:
                    # 检查是否有文本框
                    if shape.HasTextFrame:
                        text_frame = shape.TextFrame
                        if text_frame.HasText:
                            text_range = text_frame.TextRange

                            # 检查是否包含搜索文本
                            contains_text = False
                            if match_case:
                                contains_text = search_text in text_range.Text
                            else:
                                contains_text = search_text.lower() in text_range.Text.lower()

                            if contains_text:
                                # 收集匹配项（只收集前10个）
                                if len(matches) < 10:
                                    matches.append(text_range.Text.strip())

                                # 执行替换
                                # PowerPoint 的 Replace 方法会返回替换的次数
                                # 但我们没有直接访问这个返回值的方式
                                # 所以我们假设如果包含文本，就执行了替换
                                text_range.Replace(
                                    FindWhat=search_text,
                                    ReplaceWhat=replace_text,
                                    MatchCase=match_case
                                )
                                replacements += 1

            # 保存演示文稿
            output_file = save_as or file_path
            self.save_presentation(presentation, output_file)

            # 关闭演示文稿
            self.close_presentation(presentation)

            return {
                "status": "success",
                "replacements": replacements,
                "matches": matches,
                "output_file": output_file,
                "summary": "搜索替换成功"
            }

        except Exception as e:
            logger.error(
                "ppt_search_and_replace_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def get_presentation_stats(self, file_path: str) -> Dict[str, Any]:
        """
        获取 PowerPoint 演示文稿统计信息

        Args:
            file_path: 演示文稿路径

        Returns:
            {
                "status": "success" | "failed",
                "stats": {
                    "slides": 幻灯片数量,
                    "shapes": 形状总数,
                    "has_media": 是否包含媒体,
                    "file_size": 文件大小（字节）
                }
            }
        """
        try:
            presentation = self.open_presentation(file_path, read_only=True)

            if not presentation:
                return {
                    "status": "failed",
                    "error": "无法打开演示文稿"
                }

            # 统计形状总数
            total_shapes = 0
            has_media = False

            for slide in presentation.Slides:
                total_shapes += slide.Shapes.Count
                for shape in slide.Shapes:
                    # 检查是否有媒体（视频/音频）
                    if shape.Type in [16, 17]:  # msoMedia/msoPlaceholder
                        has_media = True

            stats = {
                "slides": presentation.Slides.Count,
                "shapes": total_shapes,
                "has_media": has_media
            }

            # 获取文件大小
            try:
                stats["file_size"] = os.path.getsize(file_path)
            except:
                stats["file_size"] = 0

            # 关闭演示文稿
            self.close_presentation(presentation)

            return {
                "status": "success",
                "stats": stats,
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "ppt_stats_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def list_slides(self, file_path: str) -> Dict[str, Any]:
        """
        列出演示文稿中的所有幻灯片

        Args:
            file_path: 演示文稿路径

        Returns:
            {
                "status": "success" | "failed",
                "slides": [
                    {
                        "index": 1,
                        "title": "幻灯片标题",
                        "shape_count": 形状数量
                    },
                    ...
                ]
            }
        """
        try:
            presentation = self.open_presentation(file_path, read_only=True)

            if not presentation:
                return {
                    "status": "failed",
                    "error": "无法打开演示文稿"
                }

            slides = []

            # 读取所有幻灯片
            for i, slide in enumerate(presentation.Slides):
                slide_info = {
                    "index": i + 1,
                    "title": f"幻灯片 {i + 1}",
                    "shape_count": slide.Shapes.Count
                }

                # 尝试获取标题
                try:
                    if slide.Shapes.Count > 0:
                        first_shape = slide.Shapes(1)
                        if first_shape.HasTextFrame and first_shape.TextFrame.HasText:
                            slide_info["title"] = first_shape.TextFrame.TextRange.Text.strip()
                except:
                    pass

                slides.append(slide_info)

            # 关闭演示文稿
            self.close_presentation(presentation)

            return {
                "status": "success",
                "slides": slides,
                "slide_count": len(slides),
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "ppt_list_slides_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def process_file(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        统一的文件处理接口（集成到工具系统）

        Args:
            file_path: 文件路径
            **kwargs: 操作参数
                - operation: 操作类型 (read/search_and_replace/stats/list_slides)
                - 其他参数根据 operation 不同而不同

        Returns:
            操作结果

        注意：replace 操作已废弃，统一使用 search_and_replace
        """
        operation = kwargs.get("operation", "list_slides")

        if operation == "read":
            return self.read_all_text(file_path)
        elif operation == "replace":
            # ✅ replace 操作内部调用 search_and_replace（精确匹配）
            logger.info(
                "ppt_replace_deprecated",
                message="replace操作已废弃，内部转换为search_and_replace",
                file_path=file_path
            )
            return self.search_and_replace(
                file_path,
                search_text=kwargs.get("old_text"),
                replace_text=kwargs.get("new_text", ""),
                match_case=False,
                save_as=kwargs.get("save_as")
            )
        elif operation == "search_and_replace":
            return self.search_and_replace(
                file_path,
                search_text=kwargs.get("search_text"),
                replace_text=kwargs.get("replace_text", ""),
                match_case=kwargs.get("match_case", False),
                save_as=kwargs.get("save_as")
            )
        elif operation == "stats":
            return self.get_presentation_stats(file_path)
        elif operation == "list_slides":
            return self.list_slides(file_path)
        else:
            return {
                "status": "failed",
                "error": f"未知操作: {operation}"
            }
