"""Browser Services

Provides utility services for browser automation:
- ConsoleCapture: Console log capture
- PDFExporter: PDF export functionality
- FileHandler: File upload/download operations
- TraceManager: Trace debugging
"""

from .console_capture import ConsoleCapture
from .pdf_export import PDFExporter
from .file_handler import FileHandler
from .trace_manager import TraceManager

__all__ = ["ConsoleCapture", "PDFExporter", "FileHandler", "TraceManager"]
