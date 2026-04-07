import pdfplumber
import sys

def parse_pdf_with_plumber(pdf_path):
    """使用pdfplumber解析PDF文件并提取文本内容"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"PDF文件: {pdf_path}")
            print(f"总页数: {total_pages}")
            print("="*50)
            
            for i, page in enumerate(pdf.pages):
                print(f"\n--- 第 {i+1} 页 ---")
                text = page.extract_text()
                if text:
                    print(text)
                else:
                    print("[此页无文本内容或为扫描件]")
                print("="*50)
            
        return True
    except Exception as e:
        print(f"解析PDF时出错: {e}")
        return False

if __name__ == "__main__":
    pdf_path = "/home/xckj/suyuan/backend_data_registry/uploads/01d01857-93ec-4e2d-8662-a06623a0b9a6.pdf"
    parse_pdf_with_plumber(pdf_path)