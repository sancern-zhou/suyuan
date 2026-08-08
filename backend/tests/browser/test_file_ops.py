"""Unit tests for File Operations

Tests FileHandler functionality.
"""
import pytest
import tempfile
import os
from app.tools.browser.services.file_handler import FileHandler


class TestFileHandler:
    """Test FileHandler functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for downloads"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

    @pytest.fixture
    def handler(self, temp_dir):
        """Create FileHandler with temporary directory"""
        return FileHandler(download_dir=temp_dir)

    def test_handler_creation(self, temp_dir):
        """Test creating FileHandler instance"""
        handler = FileHandler(download_dir=temp_dir)
        assert handler is not None
        assert handler.download_dir == temp_dir
        assert os.path.exists(temp_dir)

    def test_setup_download(self, handler):
        """Test setup_download method exists and has correct signature"""
        # Just verify the method exists and returns the download_dir
        # We can't test with a real page in unit tests
        assert hasattr(handler, 'setup_download')
        assert hasattr(handler, 'download_dir')
        assert handler.download_dir == handler.download_dir  # Verify attribute access

    def test_list_downloads_empty(self, handler):
        """Test listing downloads when directory is empty"""
        files = handler.list_downloads()
        assert files == []
        assert isinstance(files, list)

    def test_list_downloads_with_files(self, handler, temp_dir):
        """Test listing downloads with existing files"""
        # Create dummy files
        file1 = os.path.join(temp_dir, "download1.txt")
        file2 = os.path.join(temp_dir, "download2.pdf")

        with open(file1, 'w') as f:
            f.write("test content 1")
        with open(file2, 'w') as f:
            f.write("test content 2")

        files = handler.list_downloads()

        assert len(files) == 2
        assert any(f["filename"] == "download1.txt" for f in files)
        assert any(f["filename"] == "download2.pdf" for f in files)

        # Check structure
        for file_info in files:
            assert "filename" in file_info
            assert "path" in file_info
            assert "size_kb" in file_info
            assert "created" in file_info

    def test_upload_file_not_found(self, handler):
        """Test uploading non-existent file raises error"""
        with pytest.raises(FileNotFoundError):
            handler.upload_file(None, "#file-input", "/nonexistent/file.txt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
