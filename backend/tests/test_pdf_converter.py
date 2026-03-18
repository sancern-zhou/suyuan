"""
PDF Converter Test

Test script to verify PDF conversion functionality for Office documents.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pdf_converter import pdf_converter


async def test_pdf_converter():
    """Test PDF converter initialization"""
    print("Testing PDF Converter...")
    print(f"Output directory: {pdf_converter.output_dir}")
    print(f"Output directory exists: {pdf_converter.output_dir.exists()}")

    # Test with a sample file (if available)
    sample_docx = Path(__file__).parent.parent.parent / "backend_data" / "test.docx"

    if sample_docx.exists():
        print(f"\nConverting {sample_docx} to PDF...")
        try:
            result = await pdf_converter.convert_to_pdf(str(sample_docx))
            print(f"PDF ID: {result['pdf_id']}")
            print(f"PDF URL: {result['pdf_url']}")
            print(f"PDF Pages: {result['pages']}")
            print(f"PDF Size: {result['size']} bytes")
            print("\nPDF conversion test PASSED")
        except Exception as e:
            print(f"\nPDF conversion test FAILED: {e}")
    else:
        print(f"\nNo sample DOCX file found at {sample_docx}")
        print("Skipping conversion test")

    # Test cleanup
    print("\nTesting PDF cleanup...")
    test_pdf_id = "test_cleanup_12345"
    test_pdf_path = pdf_converter.output_dir / f"{test_pdf_id}.pdf"
    test_pdf_path.touch()  # Create empty test file
    print(f"Created test PDF: {test_pdf_path}")

    cleanup_result = pdf_converter.cleanup_pdf(test_pdf_id)
    print(f"Cleanup result: {cleanup_result}")
    print(f"Test PDF exists after cleanup: {test_pdf_path.exists()}")

    if not test_pdf_path.exists():
        print("\nPDF cleanup test PASSED")
    else:
        print("\nPDF cleanup test FAILED")


if __name__ == "__main__":
    asyncio.run(test_pdf_converter())
