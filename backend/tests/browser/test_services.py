"""Unit tests for Browser Services

Tests ConsoleCapture and PDFExporter functionality.
"""
import pytest
import tempfile
import os
from typing import Dict
from app.tools.browser.services.console_capture import ConsoleCapture
from app.tools.browser.services.pdf_export import PDFExporter


class TestConsoleCapture:
    """Test ConsoleCapture functionality"""

    def test_capture_creation(self):
        """Test creating ConsoleCapture instance"""
        capture = ConsoleCapture()
        assert capture is not None
        assert len(capture.captured_pages) == 0

    def test_capture_script_defined(self):
        """Test capture script is defined"""
        assert "console.log" in ConsoleCapture.CAPTURE_SCRIPT
        assert "console.error" in ConsoleCapture.CAPTURE_SCRIPT
        assert "__consoleLogs" in ConsoleCapture.CAPTURE_SCRIPT

    def test_max_logs_constant(self):
        """Test max logs limit is defined"""
        # The script should limit logs to prevent memory issues
        assert "__consoleMaxLogs" in ConsoleCapture.CAPTURE_SCRIPT


class TestPDFExporter:
    """Test PDFExporter functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for PDFs"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup is handled by tempfile

    def test_exporter_creation(self, temp_dir):
        """Test creating PDFExporter instance"""
        exporter = PDFExporter(output_dir=temp_dir)
        assert exporter is not None
        assert exporter.output_dir == temp_dir
        assert os.path.exists(temp_dir)

    def test_list_pdfs_empty(self, temp_dir):
        """Test listing PDFs when directory is empty"""
        exporter = PDFExporter(output_dir=temp_dir)
        pdfs = exporter.list_pdfs()
        assert pdfs == []
        assert isinstance(pdfs, list)

    def test_list_pdfs_with_files(self, temp_dir):
        """Test listing PDFs with existing files"""
        # Create dummy PDF files
        pdf1 = os.path.join(temp_dir, "test1.pdf")
        pdf2 = os.path.join(temp_dir, "test2.pdf")

        with open(pdf1, 'w') as f:
            f.write("dummy pdf content 1")
        with open(pdf2, 'w') as f:
            f.write("dummy pdf content 2")

        exporter = PDFExporter(output_dir=temp_dir)
        pdfs = exporter.list_pdfs()

        assert len(pdfs) == 2
        assert any(p["filename"] == "test1.pdf" for p in pdfs)
        assert any(p["filename"] == "test2.pdf" for p in pdfs)

        # Check structure
        for pdf_info in pdfs:
            assert "filename" in pdf_info
            assert "path" in pdf_info
            assert "size_kb" in pdf_info
            assert "created" in pdf_info


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
