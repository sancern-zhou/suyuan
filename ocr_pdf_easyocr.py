import pdf2image
import easyocr
import os

def ocr_pdf_with_easyocr(pdf_path, output_dir=None):
    """使用easyocr对PDF图片进行OCR识别"""
    try:
        # 转换PDF为图片
        print(f"正在将PDF转换为图片: {pdf_path}")
        images = pdf2image.convert_from_path(pdf_path)
        print(f"转换完成，共 {len(images)} 页")
        
        # 初始化EasyOCR（中文+英文）
        print("初始化EasyOCR引擎...")
        reader = easyocr.Reader(['ch_sim', 'en'])
        
        all_text = []
        for i, image in enumerate(images):
            print(f"正在识别第 {i+1} 页...")
            # 识别图片中的文本
            result = reader.readtext(image, detail=0)
            page_text = '\n'.join(result)
            all_text.append(f"--- 第 {i+1} 页 ---")
            all_text.append(page_text)
            all_text.append("\n")
        
        # 输出结果
        full_text = '\n'.join(all_text)
        print("\n" + "="*50)
        print("OCR识别结果：")
        print("="*50)
        print(full_text)
        
        # 保存到文件
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, 'ocr_result.txt')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            print(f"\n结果已保存到: {output_path}")
        
        return full_text
    
    except Exception as e:
        print(f"OCR识别失败: {e}")
        return None

if __name__ == "__main__":
    pdf_file = '/home/xckj/suyuan/backend_data_registry/uploads/01d01857-93ec-4e2d-8662-a06623a0b9a6.pdf'
    output_dir = '/home/xckj/suyuan'
    ocr_pdf_with_easyocr(pdf_file, output_dir)