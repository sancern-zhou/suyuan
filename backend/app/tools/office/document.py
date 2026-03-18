"""
Document Class - Word Document Editor

Encapsulates Word document editing workflow with automatic handling of
RSID, author, timestamps, and multi-file XML management.

This class provides a high-level API for editing Word documents by
manipulating the underlying XML structure.
"""

import os
import shutil
import html
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog

from app.tools.xml.xml_editor import XMLEditor, XMLNode

logger = structlog.get_logger()


class DocumentFile:
    """
    Wrapper for individual XML files within a Word document.

    Provides convenient access to document XML files like:
    - word/document.xml (main content)
    - word/styles.xml (styles)
    - word/numbering.xml (numbering)
    - word/settings.xml (settings)
    """

    def __init__(self, file_path: Path, unpacked_dir: Path, enable_rsid: bool = False, author: str = "Claude"):
        """
        Initialize DocumentFile wrapper.

        Args:
            file_path: Path to the XML file (relative to unpacked_dir)
            unpacked_dir: Root directory of unpacked document
            enable_rsid: Enable RSID auto-injection for Word documents
            author: Author name for tracked changes
        """
        self._file_path = file_path
        self._unpacked_dir = unpacked_dir
        self._full_path = unpacked_dir / file_path
        self._editor: Optional[XMLEditor] = None
        self._modified = False
        self._enable_rsid = enable_rsid
        self._author = author

    def _load(self) -> XMLEditor:
        """Load the XML file into an XMLEditor."""
        if self._editor is None:
            if not self._full_path.exists():
                raise FileNotFoundError(f"XML file not found: {self._file_path}")

            content = self._full_path.read_text(encoding='utf-8')
            self._editor = XMLEditor(content, enable_rsid=self._enable_rsid, author=self._author)

        return self._editor

    @property
    def editor(self) -> XMLEditor:
        """Get the XMLEditor for this file (loads if needed)."""
        return self._load()

    def save(self) -> None:
        """Save the XML content back to the file."""
        if self._editor is not None and self._modified:
            self._full_path.write_text(
                self._editor.to_xml(),
                encoding='utf-8'
            )
            self._modified = False

    def mark_modified(self) -> None:
        """Mark this file as modified."""
        self._modified = True

    @property
    def is_modified(self) -> bool:
        """Check if this file has been modified."""
        return self._modified

    @property
    def path(self) -> Path:
        """Get the file path."""
        return self._file_path

    @property
    def full_path(self) -> Path:
        """Get the full file path."""
        return self._full_path


class Document:
    """
    Word Document Editor with automatic RSID and metadata handling.

    Provides a high-level API for editing Word documents while
    automatically handling complex Word-specific requirements like
    RSID tracking, author information, and timestamps.

    Example:
        # Open a document
        doc = Document(unpacked_dir, author="Claude")

        # Access main document
        main_doc = doc["word/document.xml"]

        # Find and replace text
        nodes = main_doc.editor.find_text_location("旧文本")
        for node in nodes:
            main_doc.editor.update_text(node, "新文本")
            main_doc.mark_modified()

        # Save changes
        doc.save()
    """

    # Standard Word XML files
    STANDARD_FILES = [
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/settings.xml",
        "word/webSettings.xml",
        "word/fontTable.xml",
        "word/endnotes.xml",
        "word/footnotes.xml",
    ]

    def __init__(
        self,
        unpacked_dir: str | Path,
        author: str = "Claude",
        edit_time: Optional[datetime] = None,
        enable_rsid: bool = True
    ):
        """
        Initialize Document editor.

        Args:
            unpacked_dir: Path to the unpacked Word document directory
            author: Author name for edit tracking (default: "Claude")
            edit_time: Timestamp for edits (default: current time)
            enable_rsid: Enable RSID auto-injection for Word documents (default: True)
        """
        self._unpacked_dir = Path(unpacked_dir)
        self._author = author
        self._edit_time = edit_time or datetime.now()
        self._enable_rsid = enable_rsid
        self._files: Dict[str, DocumentFile] = {}

        # Verify this is a valid unpacked document
        self._validate_document()

    def _validate_document(self) -> None:
        """Verify the directory contains a valid unpacked Word document."""
        if not self._unpacked_dir.exists():
            raise ValueError(f"Directory does not exist: {self._unpacked_dir}")

        # Check for [Content_Types].xml
        content_types = self._unpacked_dir / "[Content_Types].xml"
        if not content_types.exists():
            raise ValueError(f"Not a valid Word document: missing [Content_Types].xml")

        # Check for word/document.xml
        main_doc = self._unpacked_dir / "word" / "document.xml"
        if not main_doc.exists():
            raise ValueError(f"Not a valid Word document: missing word/document.xml")

    def __getitem__(self, key: str) -> DocumentFile:
        """
        Get a document XML file by path.

        Provides dictionary-style access to document files:
            doc["word/document.xml"]
            doc["word/styles.xml"]

        Args:
            key: Relative path to the XML file (e.g., "word/document.xml")

        Returns:
            DocumentFile wrapper for the requested file
        """
        if key not in self._files:
            file_path = Path(key)
            self._files[key] = DocumentFile(
                file_path,
                self._unpacked_dir,
                enable_rsid=self._enable_rsid,
                author=self._author
            )

        return self._files[key]

    def get_main_document(self) -> DocumentFile:
        """Get the main document.xml file."""
        return self["word/document.xml"]

    def get_styles(self) -> DocumentFile:
        """Get the styles.xml file."""
        return self["word/styles.xml"]

    def get_settings(self) -> DocumentFile:
        """Get the settings.xml file."""
        return self["word/settings.xml"]

    def find_paragraphs(self, text: str) -> List[XMLNode]:
        """
        Find paragraphs containing specific text.

        This method correctly handles Word document structure where text is
        nested inside <w:r><w:t> elements within <w:p> paragraphs.

        Args:
            text: Text to search for in paragraphs

        Returns:
            List of paragraph XMLNode objects containing the text
        """
        main_doc = self.get_main_document()
        paragraphs = main_doc.editor.get_nodes(tag="w:p")

        # Filter paragraphs containing the text
        # XMLNode.text now uses recursive extraction, so this works correctly
        matches = [p for p in paragraphs if text in p.text]

        # Log search results for debugging
        logger.debug(
            "find_paragraphs_result",
            search_text=text[:100],
            total_paragraphs=len(paragraphs),
            matches_found=len(matches),
            match_details=[p.text[:50] for p in matches[:3]]  # Log first 3 matches
        )

        return matches

    def replace_text(
        self,
        search_text: str,
        replace_text: str,
        in_paragraphs: bool = True
    ) -> int:
        """
        Replace text throughout the document.

        Args:
            search_text: Text to search for
            replace_text: Replacement text
            in_paragraphs: Whether to search in paragraphs (default: True)

        Returns:
            Number of replacements made
        """
        main_doc = self.get_main_document()

        if in_paragraphs:
            # Search in text nodes within paragraphs
            paragraphs = main_doc.editor.get_nodes(tag="w:p")
            count = 0

            for para in paragraphs:
                # Get all w:t text nodes within the paragraph
                text_nodes = main_doc.editor.get_nodes(tag="w:t")

                # Filter w:t nodes that belong to this paragraph
                para_text_nodes = [tn for tn in text_nodes
                                  if self._is_node_in_paragraph(tn._node, para._node)]

                for text_node in para_text_nodes:
                    if search_text in text_node.text:
                        # Update the text
                        new_text = text_node.text.replace(search_text, replace_text)
                        if main_doc.editor.update_text(text_node, new_text):
                            count += 1

            if count > 0:
                main_doc.mark_modified()

            return count

        # Search in all text nodes
        text_nodes = main_doc.editor.find_text_location(search_text)
        count = 0

        for node in text_nodes:
            new_text = node.text.replace(search_text, replace_text)
            if main_doc.editor.update_text(node, new_text):
                count += 1

        if count > 0:
            main_doc.mark_modified()

        return count

    def _is_node_in_paragraph(self, node, paragraph) -> bool:
        """
        Check if a node is contained within a paragraph.

        Args:
            node: The DOM node to check
            paragraph: The paragraph DOM node

        Returns:
            True if node is contained within paragraph
        """
        parent = node.parentNode
        while parent:
            if parent == paragraph:
                return True
            parent = parent.parentNode
        return False

    def insert_paragraph_after(
        self,
        marker_text: str,
        new_paragraph_text: str,
        style: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Insert a new paragraph after one containing marker text.

        Args:
            marker_text: Text to search for in paragraphs
            new_paragraph_text: Text content for the new paragraph
            style: Optional paragraph style identifier

        Returns:
            (success, message) tuple where success indicates if the operation succeeded
            and message provides details about the result or error
        """
        main_doc = self.get_main_document()

        # Find the paragraph containing the marker (uses recursive text extraction)
        target_paragraphs = self.find_paragraphs(marker_text)
        if not target_paragraphs:
            error_msg = (
                f"未找到包含指定文本的段落: '{marker_text[:100]}{'...' if len(marker_text) > 100 else ''}'. "
                f"可能的原因: 1) 文本被分割到多个<w:t>节点 2) 文本中有额外空格或换行 3) 文本使用了不同的字符(如括号/引号)"
            )
            logger.warning(
                "insert_paragraph_after_no_match",
                marker_text=marker_text[:100],
                reason="No paragraphs found containing the marker text",
                suggestion="Try checking the exact text in the document, including whitespace and special characters"
            )
            return False, error_msg

        target = target_paragraphs[0]
        logger.info(
            "insert_paragraph_after_found_target",
            marker_text=marker_text[:50],
            target_position=f"line {getattr(target._node, 'parse_position', (None,))[0] if hasattr(target._node, 'parse_position') else 'unknown'}"
        )

        # Build the new paragraph XML
        if style:
            new_para_xml = f'''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:pPr><w:pStyle w:val="{style}"/></w:pPr>
                <w:r><w:t>{new_paragraph_text}</w:t></w:r>
            </w:p>'''
        else:
            new_para_xml = f'''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:r><w:t>{new_paragraph_text}</w:t></w:r>
            </w:p>'''

        # Insert after the target paragraph
        if main_doc.editor.insert_after(target, new_para_xml):
            main_doc.mark_modified()
            logger.info(
                "insert_paragraph_after_success",
                marker_text=marker_text[:50],
                new_content_preview=new_paragraph_text[:50]
            )
            return True, "段落插入成功"

        error_msg = "插入段落失败: XML 操作失败"
        logger.error(
            "insert_paragraph_after_xml_failed",
            marker_text=marker_text[:50],
            reason="insert_after returned False"
        )
        return False, error_msg

    def replace_paragraph_content(
        self,
        contains: str,
        new_content: str
    ) -> bool:
        """
        Replace the content of paragraphs containing specific text.

        Uses recursive text extraction to find paragraphs, correctly handling
        Word document structure where text is nested in <w:r><w:t> elements.

        Args:
            contains: Text that target paragraphs must contain
            new_content: New paragraph content

        Returns:
            True if successful, False otherwise
        """
        main_doc = self.get_main_document()

        # Find paragraphs using recursive text extraction
        target_paragraphs = self.find_paragraphs(contains)
        if not target_paragraphs:
            logger.warning(
                "replace_paragraph_no_match",
                search_text=contains,
                reason="No paragraphs found containing the specified text"
            )
            return False

        # Replace the first matching paragraph
        target = target_paragraphs[0]

        # Escape HTML entities to prevent XML injection
        escaped_content = html.escape(new_content, quote=True)

        # Build new paragraph XML (preserving basic structure)
        # Note: This creates a simple paragraph without preserving original formatting
        new_para_xml = f'''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:r><w:t>{escaped_content}</w:t></w:r>
        </w:p>'''

        success = main_doc.editor.replace_node(target, new_para_xml)
        if success:
            main_doc.mark_modified()
            logger.info(
                "replace_paragraph_success",
                search_text=contains,
                new_content_preview=new_content[:50]
            )
        else:
            logger.error(
                "replace_paragraph_failed",
                search_text=contains,
                reason="replace_node returned False"
            )

        return success

    def save(self) -> None:
        """
        Save all modified files back to disk.

        This writes all changes made through the XMLEditor instances
        back to their respective files in the unpacked directory.
        """
        for file_wrapper in self._files.values():
            if file_wrapper.is_modified:
                file_wrapper.save()
                logger.info(
                    "document_file_saved",
                    file=str(file_wrapper.path)
                )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the document.

        Returns:
            Dictionary with document statistics
        """
        stats = {
            "unpacked_dir": str(self._unpacked_dir),
            "author": self._author,
            "edit_time": self._edit_time.isoformat(),
            "files_loaded": len(self._files),
            "files_modified": sum(1 for f in self._files.values() if f.is_modified),
        }

        # Add main document statistics if loaded
        if "word/document.xml" in self._files:
            main_doc = self["word/document.xml"]
            stats["main_doc_stats"] = main_doc.editor.get_statistics()

        return stats

    def backup(self) -> Path:
        """
        Create a backup of the unpacked directory.

        Returns:
            Path to the backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self._unpacked_dir.name}_backup_{timestamp}"
        backup_path = self._unpacked_dir.parent / backup_name

        shutil.copytree(self._unpacked_dir, backup_path)

        logger.info(
            "document_backup_created",
            source=str(self._unpacked_dir),
            backup=str(backup_path)
        )

        return backup_path
