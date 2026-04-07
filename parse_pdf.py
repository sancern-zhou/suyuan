import PyPDF2
import sys

def parse_pdf(pdf_path):
    """解析PDF文件并提取文本内容"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            print(f"PDF文件: {pdf_path}")
            print(f"总页数: {num_pages}")
            print("=" * 50)
            
            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                print(f"\n--- 第 {page_num + 1} 页 ---")
                print(text)
                print("=" * 50)
            
            return True
    except Exception as e:
        print(f"解析PDF时出错: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = "/home/xckj/suyuan/backend_data_registry/uploads/01d01857-93ec-4e2d-8662-a06623a0b9a6.pdf"
    
    parse_pdf(pdf_path)