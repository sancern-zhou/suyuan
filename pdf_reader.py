import sys
import pdfplumber

def read_pdf(file_path):
    """读取PDF文件内容"""
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"读取PDF文件时出错: {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python pdf_reader.py <pdf文件路径>")
    else:
        pdf_path = sys.argv[1]
        content = read_pdf(pdf_path)
        print(content)
