"""
Word Win32 COM 工具

提供 Word 文档的自动化处理能力：
- 读取/替换文本（使用 wdReplaceAll，快速且安全）
- 操作表格
- 提取图片
- 批注和修订

性能优化：
- search_and_replace 使用 wdReplaceAll（一次性全部替换），比手动循环快10倍
- 无无限循环风险（Word 内部优化）
- 参考：https://stackoverflow.com/questions/26071366/speed-up-multiple-replacement
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog

from .base_win32 import Win32Base

logger = structlog.get_logger()


class WordWin32Tool(Win32Base):
    """
    Word 自动化工具

    支持的操作：
    - 读取文档内容
    - 替换文本
    - 操作表格
    - 提取图片
    - 批注和修订操作
    """

    def __init__(self, visible: bool = False):
        """
        初始化 Word 工具

        Args:
            visible: 是否显示 Word 窗口
        """
        super().__init__(
            app_name=self.APP_WORD,
            visible=visible,
            display_alerts=False
        )

    def open_document(self, file_path: str, read_only: bool = True):
        """
        打开 Word 文档

        Args:
            file_path: 文档路径
            read_only: 是否以只读方式打开

        Returns:
            Document 对象
        """
        try:
            self.ensure_initialized()

            abs_path = self.get_absolute_path(file_path)

            if not self.check_file_exists(abs_path):
                return None

            # 打开文档
            doc = self.app.Documents.Open(
                FileName=abs_path,
                ReadOnly=read_only,
                Visible=self.visible
            )

            logger.info(
                "word_document_opened",
                path=file_path,
                read_only=read_only
            )

            return doc

        except Exception as e:
            logger.error(
                "word_open_failed",
                path=file_path,
                error=str(e)
            )
            return None

    def save_document(self, doc, file_path: str):
        """
        保存 Word 文档

        Args:
            doc: Document 对象
            file_path: 保存路径
        """
        try:
            abs_path = self.get_absolute_path(file_path)

            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # 保存文档
            doc.SaveAs(FileName=abs_path)

            logger.info(
                "word_document_saved",
                path=file_path
            )

            return True

        except Exception as e:
            logger.error(
                "word_save_failed",
                path=file_path,
                error=str(e)
            )
            return False

    def close_document(self, doc, save_changes: bool = False):
        """
        关闭 Word 文档

        Args:
            doc: Document 对象
            save_changes: 是否保存更改
        """
        try:
            doc.Close(SaveChanges=-1 if save_changes else 0)
            logger.debug("word_document_closed")
        except Exception as e:
            logger.error("word_close_document_failed", error=str(e))

    def _apply_paragraph_format(self, inserted_range):
        """
        为插入的文本应用默认段落格式：两端对齐，首行缩进2字符

        Word VBA 对齐常量：
        - wdAlignParagraphLeft = 0 (左对齐)
        - wdAlignParagraphCenter = 1 (居中)
        - wdAlignParagraphRight = 2 (右对齐)
        - wdAlignParagraphJustify = 3 (两端对齐)
        - wdAlignParagraphDistribute = 4 (分散对齐)

        Args:
            inserted_range: 插入内容的 Range 对象
        """
        try:
            # 设置段落格式：两端对齐
            inserted_range.ParagraphFormat.Alignment = 3  # wdAlignParagraphJustify
            # 首行缩进2字符
            inserted_range.ParagraphFormat.CharacterUnitFirstLineIndent = 2
            logger.debug("paragraph_format_applied", alignment="justify", first_line_indent="2chars")
        except Exception as e:
            # 格式设置失败不影响插入操作的成功
            logger.warning("paragraph_format_failed", error=str(e))
        except Exception as e:
            logger.warning("word_close_warning", error=str(e))

    def read_all_text(self, file_path: str) -> Dict[str, Any]:
        """
        读取 Word 文档的所有文本（性能优化版本）

        优化说明：
        1. 使用 Content.Text + Split() 代替迭代 Paragraphs 集合（快 5-10倍）
        2. 禁用 ScreenUpdating 提升性能（快 20-50%）
        参考：https://techcommunity.microsoft.com/t5/excel/fastest-way-to-read-entire-word-text-to-array/td-p/4197159

        Args:
            file_path: 文档路径

        Returns:
            {
                "status": "success" | "failed",
                "text": "文档内容",
                "paragraphs": ["段落1", "段落2", ...],
                "stats": {
                    "paragraph_count": 段落数,
                    "word_count": 字数,
                    "char_count": 字符数
                },
                "metadata": {
                    "method": "Content.Text+Split",
                    "screen_updating": false
                }
            }
        """
        try:
            doc = self.open_document(file_path, read_only=True)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            # ✅ 性能优化：禁用屏幕更新
            with self.disable_screen_updating():
                # ✅ 性能优化：使用 Content.Text 一次性读取全部文本
                # 比迭代 Paragraphs 集合快 5-10 倍
                full_text = doc.Content.Text

                # ✅ 性能优化：使用 Split() 分割段落
                # Word 段落分隔符：\r (vbCr)
                raw_paragraphs = full_text.split('\r')

                # 过滤空段落并去除首尾空白
                paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

                # 统计信息（使用已获取的数据，避免重复 COM 调用）
                stats = {
                    "paragraph_count": len(paragraphs),
                    "word_count": len(full_text.split()),  # 简单分词统计
                    "char_count": len(full_text)
                }

                logger.info(
                    "word_read_completed",
                    path=file_path,
                    method="Content.Text+Split",
                    paragraph_count=stats["paragraph_count"],
                    char_count=stats["char_count"]
                )

            # 关闭文档
            self.close_document(doc)

            return {
                "status": "success",
                "text": full_text,
                "paragraphs": paragraphs,
                "stats": stats,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "word_processor",
                    "method": "Content.Text+Split",
                    "screen_updating": False
                },
                "summary": f"读取成功（{stats['paragraph_count']}个段落，{stats['char_count']}个字符）"
            }

        except Exception as e:
            logger.error("word_read_failed", path=file_path, error=str(e), exc_info=True)
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
        match_case: bool = False,
        match_whole_word: bool = False,
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        替换 Word 文档中的文本

        Args:
            file_path: 文档路径
            old_text: 要查找的文本
            new_text: 替换的文本
            match_case: 是否区分大小写
            match_whole_word: 是否全字匹配
            save_as: 保存为新文件（可选，不指定则覆盖原文件）

        Returns:
            {
                "status": "success" | "failed",
                "replacements": 替换次数,
                "output_file": "输出文件路径"
            }
        """
        try:
            doc = self.open_document(file_path, read_only=False)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            # 使用 Word Content.Find 进行替换（更可靠）
            find = doc.Content.Find
            find.ClearFormatting()
            find.Replacement.ClearFormatting()  # ⚠️ 关键：清除Replacement格式

            # 设置属性
            find.Text = old_text
            find.Replacement.Text = new_text
            find.Forward = True
            find.Wrap = 1  # wdFindContinue
            find.MatchCase = match_case
            find.MatchWholeWord = match_whole_word

            # 执行替换
            result = find.Execute(Replace=2)  # wdReplaceAll

            # 处理返回值：确保是整数类型
            if isinstance(result, bool):
                # 如果是布尔值，False 表示未找到，True 表示找到了但可能是0次替换
                replacements = 1 if result else 0
            else:
                replacements = int(result)

            logger.info(
                "word_replace_completed",
                path=file_path,
                search_text=old_text,
                replace_text=new_text,
                raw_result=result,
                replacements=replacements,
                result_type=type(result).__name__
            )

            # 保存文档
            output_file = save_as or file_path
            self.save_document(doc, output_file)

            # 关闭文档
            self.close_document(doc, save_changes=True)

            return {
                "status": "success",
                "replacements": replacements,
                "output_file": output_file,
                "summary": "替换成功"
            }

        except Exception as e:
            logger.error("word_replace_failed", path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def read_tables(self, file_path: str) -> Dict[str, Any]:
        """
        读取 Word 文档中的所有表格

        Args:
            file_path: 文档路径

        Returns:
            {
                "status": "success" | "failed",
                "tables": [
                    {
                        "index": 0,
                        "rows": 行数,
                        "cols": 列数,
                        "data": [["单元格", ...], ...]
                    },
                    ...
                ],
                "table_count": 表格数量
            }
        """
        try:
            doc = self.open_document(file_path, read_only=True)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            tables = []

            # 读取所有表格
            for i, table in enumerate(doc.Tables):
                table_data = {
                    "index": i,
                    "rows": table.Rows.Count,
                    "cols": table.Columns.Count,
                    "data": []
                }

                # 读取表格数据
                for row in table.Rows:
                    row_data = []
                    for cell in row.Cells:
                        row_data.append(cell.Range.Text.strip())
                    table_data["data"].append(row_data)

                tables.append(table_data)

            # 关闭文档
            self.close_document(doc)

            return {
                "status": "success",
                "tables": tables,
                "table_count": len(tables),
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error("word_read_tables_failed", path=file_path, error=str(e))
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
        match_whole_word: bool = False,
        use_wildcards: bool = False,
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        搜索并替换 Word 文档中的文本（使用 wdReplaceAll，快速且安全）

        优化说明：
        1. 使用 wdReplaceAll（快10倍，无无限循环风险）
        2. 禁用 ScreenUpdating（快20-50%）

        Args:
            file_path: 文档路径
            search_text: 要查找的文本（支持通配符）
            replace_text: 替换的文本（默认为空，即删除）
            match_case: 是否区分大小写
            match_whole_word: 是否全字匹配
            use_wildcards: 是否使用通配符（支持正则表达式）
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "replacements": 替换次数（布尔值转换：1=找到并替换，0=未找到）,
                "output_file": "输出文件路径",
                "matches": []  # wdReplaceAll 无法返回匹配列表
            }
        """
        try:
            doc = self.open_document(file_path, read_only=False)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            # ⚠️ 完全使用手动循环方法（Delete + InsertAfter）
            # 原因：wdReplaceAll 在某些 Word 版本中存在 bug，
            # 即使返回 True，实际替换也可能不生效
            # 参考：https://github.com/mhammond/pywin32/issues/726

            import uuid

            # 检查替换文本是否包含搜索文本
            replace_text_contains_search = search_text in replace_text

            logger.info(
                "word_replace_start",
                path=file_path,
                search_text=search_text,
                search_text_repr=repr(search_text),
                search_text_bytes=search_text.encode('utf-8').hex(),
                replace_text_length=len(replace_text),
                replace_text_preview=replace_text[:100] + "..." if len(replace_text) > 100 else replace_text,
                replace_text_contains_search=replace_text_contains_search,
                method="manual_delete_insert"
            )

            # 如果替换文本包含搜索文本，使用两步策略（避免无限循环）
            if replace_text_contains_search:
                # 生成一个唯一的占位符（确保不会出现在文档中）
                placeholder = f"__TEMP_REPLACE_{uuid.uuid4().hex}__"

                logger.info(
                    "word_replace_using_placeholder",
                    placeholder=placeholder,
                    reason="replace_text_contains_search=True"
                )

                # 第一步：将搜索文本替换为占位符
                find = doc.Content.Find
                find.ClearFormatting()
                find.Text = search_text
                find.Forward = True
                find.Wrap = 1
                find.MatchCase = match_case
                find.MatchWholeWord = match_whole_word
                find.MatchWildcards = use_wildcards

                replacements_step1 = 0
                last_position = 0
                MAX_ITERATIONS = 100

                while find.Execute():
                    # 先获取找到的范围，避免后续操作导致对象失效
                    try:
                        # 使用 Selection 或直接使用 find 的结果
                        found_start = find.Parent.Start
                        found_end = find.Parent.End
                        found_range = doc.Range(found_start, found_end)
                    except Exception as e:
                        logger.error("word_replace_get_range_failed", error=str(e))
                        break

                    current_position = found_range.Start

                    if current_position <= last_position:
                        break

                    last_position = current_position
                    found_range.Delete()
                    found_range.InsertAfter(placeholder)
                    replacements_step1 += 1

                    # 更新查找位置到插入点之后
                    try:
                        find.Parent.Start = found_range.End
                        find.Parent.End = doc.Content.End
                    except Exception as e:
                        logger.error("word_replace_update_find_position_failed", error=str(e))
                        break

                    if replacements_step1 >= MAX_ITERATIONS:
                        logger.error("word_replace_placeholder_max_iterations")
                        break

                logger.info("word_replace_step1_completed", placeholder_replacements=replacements_step1)

                # 第二步：将占位符替换为目标文本
                find.Text = placeholder
                replacements_step2 = 0
                last_position = 0

                while find.Execute():
                    # 先获取找到的范围，避免后续操作导致对象失效
                    try:
                        found_start = find.Parent.Start
                        found_end = find.Parent.End
                        found_range = doc.Range(found_start, found_end)
                    except Exception as e:
                        logger.error("word_replace_get_range_failed", error=str(e))
                        break

                    current_position = found_range.Start

                    if current_position <= last_position:
                        break

                    last_position = current_position
                    found_range.Delete()
                    found_range.InsertAfter(replace_text)
                    replacements_step2 += 1

                    # 更新查找位置到插入点之后
                    try:
                        find.Parent.Start = found_range.End
                        find.Parent.End = doc.Content.End
                    except Exception as e:
                        logger.error("word_replace_update_find_position_failed", error=str(e))
                        break

                    if replacements_step2 >= MAX_ITERATIONS:
                        logger.error("word_replace_final_max_iterations")
                        break

                replacements = replacements_step2
                logger.info("word_replace_step2_completed", final_replacements=replacements)

            else:
                # 替换文本不包含搜索文本，直接使用手动循环
                logger.info(
                    "word_replace_direct_loop",
                    path=file_path,
                    search_text=search_text,
                    replace_text_length=len(replace_text),
                    method="delete_and_insert"
                )

                find = doc.Content.Find
                find.ClearFormatting()
                find.Text = search_text
                find.Forward = True
                find.Wrap = 1
                find.MatchCase = match_case
                find.MatchWholeWord = match_whole_word
                find.MatchWildcards = use_wildcards

                replacements = 0
                last_position = 0
                MAX_ITERATIONS = 100  # 降低限制，便于观察

                logger.info(
                    "word_replace_manual_loop_start",
                    path=file_path,
                    search_text=search_text,
                    replace_text_length=len(replace_text),
                    replace_text_preview=replace_text[:100] + "..." if len(replace_text) > 100 else replace_text
                )

                # 循环查找并替换（带详细日志）
                while find.Execute():
                    # 先获取找到的范围，避免后续操作导致对象失效
                    try:
                        found_start = find.Parent.Start
                        found_end = find.Parent.End
                        found_range = doc.Range(found_start, found_end)
                    except Exception as e:
                        logger.error("word_replace_get_range_failed", error=str(e), exc_info=True)
                        break

                    current_position = found_range.Start

                    logger.info(
                        "word_replace_iteration",
                        iteration=replacements + 1,
                        found_start=found_range.Start,
                        found_end=found_range.End,
                        current_position=current_position,
                        last_position=last_position
                    )

                    # ⚠️ 位置保护：避免重复处理同一位置
                    if current_position <= last_position:
                        logger.error(
                            "word_replace_position_regression",
                            iterations=replacements,
                            last_position=last_position,
                            current_position=current_position,
                            error="Position did not advance, breaking loop"
                        )
                        break

                    last_position = current_position

                    # 删除找到的文本
                    try:
                        found_range.Delete()
                        logger.debug("word_replace_delete_success")
                    except Exception as e:
                        logger.error("word_replace_delete_failed", error=str(e), exc_info=True)
                        break

                    # 在原位置插入新文本
                    try:
                        found_range.InsertAfter(replace_text)
                        logger.debug(
                            "word_replace_insert_success",
                            new_text_length=len(replace_text)
                        )
                    except Exception as e:
                        logger.error("word_replace_insert_failed", error=str(e), exc_info=True)
                        break

                    replacements += 1

                    # 重置查找位置到插入点之后
                    try:
                        find.Parent.Start = found_range.End
                        find.Parent.End = doc.Content.End
                    except Exception as e:
                        logger.error("word_replace_update_find_position_failed", error=str(e), exc_info=True)
                        break

                    # 防止意外无限循环
                    if replacements >= MAX_ITERATIONS:
                        logger.error(
                            "word_replace_max_iterations",
                            path=file_path,
                            iterations=replacements,
                            max_iterations=MAX_ITERATIONS,
                            error="Reached maximum iterations limit"
                        )
                        break

                logger.info(
                    "word_replace_completed",
                    path=file_path,
                    search_text=search_text,
                    replace_text=replace_text[:50] + "..." if len(replace_text) > 50 else replace_text,
                    replacements=replacements,
                    method="delete_and_insert",
                    screen_updating=False
                )

            # 保存文档
            output_file = save_as or file_path
            self.save_document(doc, output_file)

            # 关闭文档
            self.close_document(doc, save_changes=True)

            return {
                "status": "success",
                "replacements": replacements,
                "output_file": output_file,
                "matches": [],  # 手动循环无法返回匹配列表
                "summary": f"替换成功（{replacements}处）" if replacements > 0 else "未找到匹配文本"
            }

        except Exception as e:
            logger.error("word_search_and_replace_failed", path=file_path, error=str(e), exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def batch_replace(
        self,
        file_path: str,
        replacements: Dict[str, str],
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量替换 Word 文档中的文本

        Args:
            file_path: 文档路径
            replacements: 替换字典 {"旧文本": "新文本", ...}
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "results": [
                    {"old": "旧文本", "new": "新文本", "count": 替换次数},
                    ...
                ],
                "total_replacements": 总替换次数
            }
        """
        try:
            doc = self.open_document(file_path, read_only=False)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            results = []
            total_replacements = 0

            # 批量替换（使用手动循环方法）
            for old_text, new_text in replacements.items():
                # 使用手动循环方法（Delete + InsertAfter）
                find = doc.Content.Find
                find.ClearFormatting()
                find.Text = old_text
                find.Forward = True
                find.Wrap = 1
                find.MatchCase = False
                find.MatchWholeWord = False

                count = 0
                last_position = 0
                MAX_ITERATIONS = 100

                while find.Execute():
                    found_range = doc.Range(find.Parent.Start, find.Parent.End)
                    current_position = found_range.Start

                    if current_position <= last_position:
                        break

                    last_position = current_position
                    found_range.Delete()
                    found_range.InsertAfter(new_text)
                    count += 1

                    find.Parent.Start = found_range.End
                    find.Parent.End = doc.Content.End

                    if count >= MAX_ITERATIONS:
                        break

                results.append({
                    "old": old_text,
                    "new": new_text[:50] + "..." if len(new_text) > 50 else new_text,
                    "count": count
                })
                total_replacements += count

            # 保存文档
            output_file = save_as or file_path
            self.save_document(doc, output_file)

            # 关闭文档
            self.close_document(doc, save_changes=True)

            return {
                "status": "success",
                "results": results,
                "total_replacements": total_replacements,
                "output_file": output_file,
                "summary": "批量替换成功"
            }

        except Exception as e:
            logger.error("word_batch_replace_failed", path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def get_document_stats(self, file_path: str) -> Dict[str, Any]:
        """
        获取 Word 文档统计信息

        Args:
            file_path: 文档路径

        Returns:
            {
                "status": "success" | "failed",
                "stats": {
                    "pages": 页数,
                    "words": 字数,
                    "characters": 字符数,
                    "paragraphs": 段落数,
                    "tables": 表格数,
                    "images": 图片数
                }
            }
        """
        try:
            doc = self.open_document(file_path, read_only=True)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            stats = {
                "pages": doc.ComputeStatistics(2),  # wdStatisticPages
                "words": doc.ComputeStatistics(0),  # wdStatisticWords
                "characters": doc.ComputeStatistics(3),  # wdStatisticCharacters
                "paragraphs": doc.Paragraphs.Count,
                "tables": doc.Tables.Count,
                "images": doc.InlineShapes.Count
            }

            # 关闭文档
            self.close_document(doc)

            return {
                "status": "success",
                "stats": stats,
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error("word_stats_failed", path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def extract_images(
        self,
        file_path: str,
        output_dir: str = None
    ) -> Dict[str, Any]:
        """
        提取 Word 文档中的所有图片（统一使用 HTML 导出方法）

        使用 HTML 导出方法，可以同时提取：
        - InlineShapes（内联图片）
        - Shapes（浮动图片）

        Args:
            file_path: Word 文档路径
            output_dir: 输出目录（默认为 backend_data_registry/temp_images）

        Returns:
            {
                "status": "success",
                "images": [
                    {
                        "index": 0,
                        "path": "D:/溯源/backend_data_registry/temp_images/doc_image_0.png",
                        "width": 0,
                        "height": 0
                    },
                    ...
                ],
                "count": 3,
                "summary": "提取了3张图片"
            }
        """
        import shutil
        import tempfile

        try:
            doc = self.open_document(file_path, read_only=True)
            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            # 设置默认输出目录（查找项目根目录）
            if not output_dir:
                # 从当前文件向上查找项目根目录
                # 查找包含 "backend" 文件夹的目录作为项目根目录
                current_path = Path(__file__).resolve()
                base_dir = None

                # 最多向上查找 5 级
                for _ in range(5):
                    if current_path.name == "backend":
                        base_dir = current_path.parent
                        break
                    current_path = current_path.parent

                # 如果找不到，使用当前位置的上级目录（兼容性）
                if not base_dir:
                    base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent

                output_dir = base_dir / "backend_data_registry" / "temp_images"
            else:
                output_dir = Path(output_dir).resolve()

            # 记录路径信息，便于调试
            logger.info(
                "word_extract_images_path",
                output_dir=str(output_dir),
                base_dir=str(base_dir) if 'base_dir' in locals() else "N/A"
            )

            output_dir.mkdir(parents=True, exist_ok=True)

            # 使用 HTML 导出方法提取所有图片
            logger.info(
                "word_using_html_export_method",
                reason="统一方法，支持所有图片类型",
                inline_shapes=doc.InlineShapes.Count,
                shapes=doc.Shapes.Count
            )

            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp(prefix="word_html_"))

            try:
                # 导出为 HTML (格式 8 = wdFormatHTML)
                html_path = temp_dir / "temp.html"
                doc.SaveAs2(str(html_path), FileFormat=8)

                # 查找图片文件夹（通常是 filename.files）
                image_folder = None
                for item in temp_dir.iterdir():
                    if item.is_dir() and item.name.endswith('.files'):
                        image_folder = item
                        break

                images = []
                file_stem = Path(file_path).stem

                if image_folder and image_folder.exists():
                    # 查找所有图片文件（严格过滤，只保留真正的图片格式）
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
                    # 排除非图片文件的扩展名
                    excluded_extensions = ['.xml', '.html', '.htm', '.css', '.thmx', '.js']

                    all_image_files = []
                    for ext in image_extensions:
                        for file in image_folder.glob(f"*{ext}"):
                            # 额外检查：确保文件扩展名不包含排除的扩展名
                            if file.suffix.lower() not in excluded_extensions:
                                all_image_files.append(file)

                    logger.info(
                        "word_html_export_found_all_files",
                        count=len(all_image_files),
                        total_files=len(list(image_folder.iterdir()))
                    )

                    # 去重：Word 导出时可能为同一图片生成多个格式
                    # 观察到的模式：
                    # - image001.png, image002.gif -> 同一张图片
                    # - image003.png, image004.gif -> 同一张图片
                    # - 奇数编号通常是 PNG（高分辨率），偶数编号是 GIF（压缩版本）
                    # 策略：只保留奇数编号的图片，或者优先选择 PNG/JPG 格式

                    # 按文件名中的数字编号分组
                    from collections import defaultdict
                    import re

                    # 将相邻的编号配对：(1,2), (3,4), (5,6)...
                    image_files_map = {}  # {base_number: [file1, file2]}
                    for img_file in all_image_files:
                        # 提取文件名中的数字（例如 image001.png -> 1）
                        match = re.search(r'(\d+)', img_file.stem)
                        if match:
                            number = int(match.group(1))
                            # 将 1,2 -> base=0; 3,4 -> base=1; 5,6 -> base=2
                            base_number = (number - 1) // 2
                            if base_number not in image_files_map:
                                image_files_map[base_number] = []
                            image_files_map[base_number].append(img_file)
                        else:
                            # 没有数字的文件，单独处理
                            base_number = 999999
                            if base_number not in image_files_map:
                                image_files_map[base_number] = []
                            image_files_map[base_number].append(img_file)

                    logger.info(
                        "word_html_export_image_groups_paired",
                        groups=len(image_files_map),
                        example={k: [f.name for f in v] for k, v in list(image_files_map.items())[:3]}
                    )

                    # 对每组图片，选择最佳格式
                    image_files = []
                    preferred_order = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']

                    for base_number in sorted(image_files_map.keys()):
                        files = image_files_map[base_number]
                        if base_number == 999999:
                            # 无编号文件，全部保留
                            image_files.extend(files)
                        else:
                            # 按优先级选择一种格式
                            files_by_ext = {f.suffix.lower(): f for f in files}
                            for ext in preferred_order:
                                if ext in files_by_ext:
                                    selected_file = files_by_ext[ext]
                                    image_files.append(selected_file)
                                    logger.debug(
                                        "word_html_export_selected_image",
                                        base_number=base_number,
                                        selected_ext=ext,
                                        available_exts=list(files_by_ext.keys()),
                                        selected_file=selected_file.name
                                    )
                                    break

                    logger.info(
                        "word_html_export_after_dedup",
                        count=len(image_files),
                        original_count=len(all_image_files)
                    )

                    # 按文件名排序，确保顺序一致
                    image_files.sort(key=lambda x: x.name)

                    # 复制图片到输出目录并重命名
                    # 使用连续的显示编号（从1开始），不再使用原始编号
                    for display_idx, img_file in enumerate(image_files, start=1):
                        dest_file = output_dir / f"{file_stem}_{display_idx}{img_file.suffix}"
                        shutil.copy2(img_file, dest_file)

                        # 使用 PIL 获取实际图片尺寸
                        width, height = 0, 0
                        try:
                            from PIL import Image
                            with Image.open(dest_file) as img:
                                width, height = img.size
                        except Exception as e:
                            logger.debug(f"无法获取图片尺寸: {e}")

                        images.append({
                            "index": display_idx - 1,  # 返回的索引从 0 开始
                            "path": str(dest_file),
                            "width": width,
                            "height": height,
                            "type": "image"
                        })

                        logger.info(
                            "word_image_copied",
                            index=display_idx,  # 日志编号从1开始
                            source=str(img_file.name),
                            dest=str(dest_file),
                            width=width,
                            height=height
                        )

                self.close_document(doc)

                return {
                    "status": "success",
                    "images": images,
                    "count": len(images),
                    "summary": f"提取了{len(images)}张图片"
                }

            finally:
                # 清理临时目录
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            logger.error("word_extract_images_failed", path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": str(e),
                "summary": "图片提取失败"
            }

    def insert_text(
        self,
        file_path: str,
        content: str,
        position: str = "end",
        target: str = None,
        save_as: Optional[str] = None,
        target_type: str = "text",
        target_index: int = None
    ) -> Dict[str, Any]:
        """
        在 Word 文档中插入文本内容（支持表格/图片定位）

        Args:
            file_path: 文档路径
            content: 要插入的内容
            position: 插入位置
                - "end": 文档末尾（默认）
                - "start": 文档开头
                - "after": 在目标之后
                - "before": 在目标之前
            target: 目标文本（当 position="after" 或 "before" 且 target_type="text" 时必需）
            save_as: 保存为新文件（可选）
            target_type: 目标类型（用于 position="after"/"before"）
                - "text": 文本目标（默认，使用target参数）
                - "table": 表格目标（使用target_index参数）
                - "image": 图片目标（使用target_index参数）
            target_index: 目标索引（从0开始，target_type="table"或"image"时必需）

        Returns:
            {
                "status": "success" | "failed",
                "inserted": True,
                "insert_position": "start|end|after|before",
                "target_type": "text|table|image",
                "target_index": int,
                "output_file": "输出文件路径"
            }
        """
        try:
            doc = self.open_document(file_path, read_only=False)

            if not doc:
                return {
                    "status": "failed",
                    "error": "无法打开文档",
                    "summary": "操作失败"
                }

            # ✅ 性能优化：禁用屏幕更新（在大段文本插入时效果显著）
            with self.disable_screen_updating():
                # 根据位置插入内容
                if position == "end":
                    # 在文档末尾插入
                    doc.Content.InsertAfter(content)
                    # 获取插入的内容并应用段落格式
                    inserted_range = doc.Range(doc.Content.End - len(content), doc.Content.End)
                    self._apply_paragraph_format(inserted_range)
                    logger.info("word_insert_end", file_path=file_path, content_length=len(content))

                elif position == "start":
                    # 在文档开头插入
                    doc.Content.InsertBefore(content)
                    # 获取插入的内容并应用段落格式
                    inserted_range = doc.Range(0, len(content))
                    self._apply_paragraph_format(inserted_range)
                    logger.info("word_insert_start", file_path=file_path, content_length=len(content))

                elif position == "after":
                    # 在目标之后插入（支持文本/表格/图片）
                    if target_type == "text":
                        if not target:
                            return {
                                "status": "failed",
                                "error": "target_type='text' 时需要提供 target 参数",
                                "summary": "操作失败"
                            }
                        # 文本目标：使用Find查找
                        find = doc.Content.Find
                        find.Text = target
                        find.Forward = True

                        if find.Execute():
                            found_range = doc.Range(find.Parent.Start, find.Parent.End)
                            insert_pos = found_range.End
                            doc.Range(insert_pos, insert_pos).InsertAfter(content)
                            # 获取插入的内容并应用段落格式
                            inserted_range = doc.Range(insert_pos, insert_pos + len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_after_text",
                                file_path=file_path,
                                target=target,
                                content_length=len(content)
                            )
                        else:
                            return {
                                "status": "failed",
                                "error": f"未找到目标文本: {target}",
                                "summary": "操作失败"
                            }

                    elif target_type == "table":
                        if target_index is None:
                            return {
                                "status": "failed",
                                "error": "target_type='table' 时需要提供 target_index 参数",
                                "summary": "操作失败"
                            }
                        try:
                            # Word表格索引从1开始
                            table = doc.Tables(target_index + 1)
                            # 在表格之后插入内容（使用table.Range.End定位到表格结束位置）
                            after_table_pos = table.Range.End
                            # 在表格结束位置插入换行和内容
                            doc.Range(after_table_pos, after_table_pos).InsertAfter("\n" + content)
                            # 获取插入的内容并应用段落格式（跳过换行符）
                            inserted_range = doc.Range(after_table_pos + 1, after_table_pos + 1 + len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_after_table",
                                file_path=file_path,
                                target_index=target_index,
                                content_length=len(content)
                            )
                        except Exception as e:
                            return {
                                "status": "failed",
                                "error": f"无法访问表格索引{target_index}: {str(e)}",
                                "summary": "操作失败"
                            }

                    elif target_type == "image":
                        if target_index is None:
                            return {
                                "status": "failed",
                                "error": "target_type='image' 时需要提供 target_index 参数",
                                "summary": "操作失败"
                            }
                        try:
                            # InlineShapes索引从1开始
                            shape = doc.InlineShapes(target_index + 1)
                            # 在图片之后插入内容（使用shape.Range.End定位到图片结束位置）
                            after_image_pos = shape.Range.End
                            doc.Range(after_image_pos, after_image_pos).InsertAfter("\n" + content)
                            # 获取插入的内容并应用段落格式（跳过换行符）
                            inserted_range = doc.Range(after_image_pos + 1, after_image_pos + 1 + len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_after_image",
                                file_path=file_path,
                                target_index=target_index,
                                content_length=len(content)
                            )
                        except Exception as e:
                            return {
                                "status": "failed",
                                "error": f"无法访问图片索引{target_index}: {str(e)}",
                                "summary": "操作失败"
                            }

                    else:
                        return {
                            "status": "failed",
                            "error": f"不支持的 target_type: {target_type}（支持: text/table/image）",
                            "summary": "操作失败"
                        }

                elif position == "before":
                    # 在目标之前插入（支持文本/表格/图片）
                    if target_type == "text":
                        if not target:
                            return {
                                "status": "failed",
                                "error": "target_type='text' 时需要提供 target 参数",
                                "summary": "操作失败"
                            }
                        # 文本目标：使用Find查找
                        find = doc.Content.Find
                        find.Text = target
                        find.Forward = True

                        if find.Execute():
                            found_range = doc.Range(find.Parent.Start, find.Parent.End)
                            insert_pos = found_range.Start
                            doc.Range(insert_pos, insert_pos).InsertBefore(content)
                            # 获取插入的内容并应用段落格式
                            inserted_range = doc.Range(insert_pos, insert_pos + len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_before_text",
                                file_path=file_path,
                                target=target,
                                content_length=len(content)
                            )
                        else:
                            return {
                                "status": "failed",
                                "error": f"未找到目标文本: {target}",
                                "summary": "操作失败"
                            }

                    elif target_type == "table":
                        if target_index is None:
                            return {
                                "status": "failed",
                                "error": "target_type='table' 时需要提供 target_index 参数",
                                "summary": "操作失败"
                            }
                        try:
                            # Word表格索引从1开始
                            table = doc.Tables(target_index + 1)
                            # 获取表格之前的段落（使用GoBack方法）
                            # table.Range.Start - 1 可以定位到表格之前的字符位置
                            before_table_pos = table.Range.Start - 1
                            if before_table_pos >= 0:
                                # 在表格之前插入内容并换行
                                doc.Range(before_table_pos, before_table_pos).InsertAfter("\n" + content)
                                # 获取插入的内容并应用段落格式（跳过换行符）
                                inserted_range = doc.Range(before_table_pos + 1, before_table_pos + 1 + len(content))
                            else:
                                # 表格在文档开头，直接在表格前插入
                                doc.Range(0, 0).InsertBefore(content + "\n")
                                # 获取插入的内容并应用段落格式
                                inserted_range = doc.Range(0, len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_before_table",
                                file_path=file_path,
                                target_index=target_index,
                                content_length=len(content)
                            )
                        except Exception as e:
                            return {
                                "status": "failed",
                                "error": f"无法访问表格索引{target_index}: {str(e)}",
                                "summary": "操作失败"
                            }

                    elif target_type == "image":
                        if target_index is None:
                            return {
                                "status": "failed",
                                "error": "target_type='image' 时需要提供 target_index 参数",
                                "summary": "操作失败"
                            }
                        try:
                            # InlineShapes索引从1开始
                            shape = doc.InlineShapes(target_index + 1)
                            # 在图片之前插入内容（使用shape.Range.Start定位到图片开始位置）
                            before_image_pos = shape.Range.Start - 1
                            if before_image_pos >= 0:
                                doc.Range(before_image_pos, before_image_pos).InsertAfter("\n" + content)
                                # 获取插入的内容并应用段落格式（跳过换行符）
                                inserted_range = doc.Range(before_image_pos + 1, before_image_pos + 1 + len(content))
                            else:
                                # 图片在文档开头，直接在图片前插入
                                doc.Range(0, 0).InsertBefore(content + "\n")
                                # 获取插入的内容并应用段落格式
                                inserted_range = doc.Range(0, len(content))
                            self._apply_paragraph_format(inserted_range)
                            logger.info(
                                "word_insert_before_image",
                                file_path=file_path,
                                target_index=target_index,
                                content_length=len(content)
                            )
                        except Exception as e:
                            return {
                                "status": "failed",
                                "error": f"无法访问图片索引{target_index}: {str(e)}",
                                "summary": "操作失败"
                            }

                    else:
                        return {
                            "status": "failed",
                            "error": f"不支持的 target_type: {target_type}（支持: text/table/image）",
                            "summary": "操作失败"
                        }

                else:
                    # 返回简洁的错误信息（执行器层会统一增强）
                    return {
                        "status": "failed",
                        "error": f"不支持的 position 值: {position}（支持: end, start, after, before）",
                        "summary": "操作失败"
                    }

            # 保存文档（在 with 块外，确保已经完成所有插入操作）
            output_file = save_as or file_path
            self.save_document(doc, output_file)

            # 关闭文档
            self.close_document(doc, save_changes=True)

            return {
                "status": "success",
                "inserted": True,
                "insert_position": position,
                "target": target,
                "target_type": target_type,
                "target_index": target_index,
                "output_file": output_file,
                "summary": "插入成功"
            }

        except Exception as e:
            logger.error("word_insert_failed", path=file_path, error=str(e))
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
                - operation: 操作类型 (read/search_and_replace/tables/stats/batch_replace)
                - 其他参数根据 operation 不同而不同

        Returns:
            操作结果

        注意：replace 操作已废弃，统一使用 search_and_replace
        """
        operation = kwargs.get("operation", "read")

        if operation == "read":
            return self.read_all_text(file_path)
        elif operation == "insert":
            return self.insert_text(
                file_path,
                content=kwargs.get("content", ""),
                position=kwargs.get("position", "end"),
                target=kwargs.get("target"),
                save_as=kwargs.get("save_as"),
                target_type=kwargs.get("target_type", "text"),
                target_index=kwargs.get("target_index")
            )
        elif operation == "replace":
            # ✅ replace 操作内部调用 search_and_replace（精确匹配，不使用通配符）
            # 这样可以统一接口，同时保持向后兼容
            logger.info(
                "word_replace_deprecated",
                message="replace操作已废弃，内部转换为search_and_replace（use_wildcards=False）",
                file_path=file_path
            )
            return self.search_and_replace(
                file_path,
                search_text=kwargs.get("old_text"),
                replace_text=kwargs.get("new_text", ""),
                match_case=False,
                match_whole_word=False,
                use_wildcards=False,  # 精确匹配
                save_as=kwargs.get("save_as")
            )
        elif operation == "tables":
            return self.read_tables(file_path)
        elif operation == "stats":
            return self.get_document_stats(file_path)
        elif operation == "batch_replace":
            return self.batch_replace(
                file_path,
                replacements=kwargs.get("replacements", {}),
                save_as=kwargs.get("save_as")
            )
        elif operation == "search_and_replace":
            return self.search_and_replace(
                file_path,
                search_text=kwargs.get("search_text"),
                replace_text=kwargs.get("replace_text", ""),
                match_case=kwargs.get("match_case", False),
                match_whole_word=kwargs.get("match_whole_word", False),
                use_wildcards=kwargs.get("use_wildcards", False),
                save_as=kwargs.get("save_as")
            )
        else:
            return {
                "status": "failed",
                "error": f"未知操作: {operation}",
                "summary": "操作失败"
            }
