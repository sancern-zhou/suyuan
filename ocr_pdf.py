import pdf2image
import pytesseract
from PIL import Image
import os

def ocr_pdf(pdf_path, output_dir='/tmp/ocr_output'):
    """使用OCR识别PDF中的文本（需要Tesseract OCR引擎）"""
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 将PDF转换为图片
    images = pdf2image.convert_from_path(pdf_path)
    print(f'Converted PDF to {len(images)} images')
    
    # 检查Tesseract是否可用
    try:
        tesseract_path = pytesseract.get_tesseract_executable() if hasattr(pytesseract, 'get_tesseract_executable') else None
        if tesseract_path:
            print(f'Tesseract found at: {tesseract_path}')
        else:
            print('Tesseract not found. Please install Tesseract OCR engine.')
            return None
    except Exception as e:
        print(f'Error checking Tesseract: {e}')
        return None
    
    # 对每页图片进行OCR
    all_text = []
    for i, image in enumerate(images):
        # 保存图片（可选）
        image_path = os.path.join(output_dir, f'page_{i+1}.png')
        image.save(image_path)
        
        # OCR识别
        text = pytesseract.image_to_string(image, lang='chi_sim+eng')
        all_text.append(text)
        print(f'Page {i+1} OCR completed')
    
    # 保存识别结果
    output_file = os.path.join(output_dir, 'ocr_result.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, text in enumerate(all_text):
            f.write(f'--- Page {i+1} ---\n')
            f.write(text)
            f.write('\n\n')
    
    print(f'OCR completed. Results saved to: {output_file}')
    return output_file

if __name__ == '__main__':
    pdf_path = '/home/xckj/suyuan/backend_data_registry/uploads/01d01857-93ec-4e2d-8662-a06623a0b9a6.pdf'
    result = ocr_pdf(pdf_path)
    if result:
        print(f'Result file: {result}')
    else:
        print('OCR failed. Please install Tesseract OCR engine.')