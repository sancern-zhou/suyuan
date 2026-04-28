"""
文档处理器

使用Unstructured进行文档解析，LlamaIndex进行智能分块。
支持格式：PDF, DOCX, XLSX, PPTX, HTML, TXT, MD, CSV, JSON

分块策略：
- llm: LLM智能分块（默认，质量最高）
- sentence: 按句子边界分块
- semantic: 基于Embedding语义相似度分块
- markdown: 按Markdown标题层级分块
- hybrid: 多层级混合分块
- llm: LLM智能分块（最精准但较慢）
"""

import os
import json
import re
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
from enum import Enum
import structlog

logger = structlog.get_logger()

# 是否在日志中完整输出LLM返回内容/JSON片段（默认开启，便于排查分块解析问题）
LLM_CHUNK_LOG_FULL = os.getenv("LLM_CHUNK_LOG_FULL", "true").lower() == "true"


class LLMMode(str, Enum):
    """LLM分块模式"""
    LOCAL = "local"    # 本地千问3
    ONLINE = "online"  # 线上API（DeepSeek/MiniMax/Mimo等）


# LLM分块的最大字符数限制（从.env配置读取）
LLM_CHUNK_MAX_CHARS_LOCAL = int(os.getenv("LLM_CHUNK_MAX_CHARS_LOCAL"))
LLM_CHUNK_MAX_CHARS_ONLINE = int(os.getenv("LLM_CHUNK_MAX_CHARS_ONLINE"))

# 线上LLM配置
ONLINE_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")  # deepseek, minimax, openai, mimo


class DocumentProcessor:
    """
    文档处理器

    使用 Unstructured 进行文档解析
    使用 LlamaIndex 进行智能分块
    """

    # 支持的文件类型
    SUPPORTED_TYPES = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "doc",
        ".xlsx": "xlsx",
        ".xls": "xls",
        ".pptx": "pptx",
        ".ppt": "ppt",
        ".html": "html",
        ".htm": "html",
        ".txt": "txt",
        ".md": "markdown",
        ".csv": "csv",
        ".json": "json",
        ".xml": "xml",
        ".rtf": "rtf"
    }

    # OCR 配置（阿里云百炼 - Qwen3-VL）
    OCR_API_URL = os.getenv("QWEN_VL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    OCR_API_KEY = os.getenv("QWEN_VL_API_KEY", "")
    OCR_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-max-latest")  # 修复：统一使用QWEN_VL_MODEL
    OCR_MAX_CONCURRENT = int(os.getenv("OCR_MAX_CONCURRENT", "2"))
    OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "120"))
    
    def __init__(self):
        self._unstructured = None
        self._embedding_model = None

        # 配置Tesseract OCR路径（Windows本地）
        self._configure_tesseract()

    def _configure_tesseract(self):
        """配置Tesseract OCR"""
        try:
            import pytesseract
            
            # 尝试从环境变量获取路径
            tesseract_cmd = os.getenv("TESSERACT_CMD")
            
            # 如果没有环境变量，尝试常见路径
            if not tesseract_cmd or not os.path.exists(tesseract_cmd):
                common_paths = [
                    r"D:\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        tesseract_cmd = path
                        break
            
            if tesseract_cmd and os.path.exists(tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                logger.info("tesseract_configured", path=tesseract_cmd)
                
                # 设置 tessdata 路径
                tessdata = os.getenv("TESSDATA_PREFIX")
                if not tessdata:
                    tessdata = os.path.join(os.path.dirname(tesseract_cmd), "tessdata")
                if os.path.exists(tessdata):
                    os.environ["TESSDATA_PREFIX"] = tessdata
            else:
                logger.warning("tesseract_not_found")
                
        except ImportError:
            logger.warning("pytesseract_not_installed")

    def _html_table_to_text(self, html: str) -> str:
        """将HTML表格转换为文本格式"""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table')
            if not table:
                return html
            
            rows = []
            for tr in table.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cell_text = td.get_text(strip=True)
                    cells.append(cell_text)
                if cells:
                    rows.append(' | '.join(cells))
            
            return '\n'.join(rows)
        except Exception as e:
            logger.warning("html_table_parse_failed", error=str(e))
            return html

    def _extract_tables_with_gmft(self, file_path: str) -> List[str]:
        """使用 gmft (基于 Microsoft Table Transformer) 从 PDF 中提取表格"""
        try:
            # 设置环境变量（确保可以加载模型）
            os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
            os.environ.setdefault('HF_HUB_OFFLINE', '0')
            os.environ.setdefault('TRANSFORMERS_OFFLINE', '0')
            
            from gmft.auto import TableDetector, AutoTableFormatter
            from gmft.pdf_bindings import PyPDFium2Document
            
            # 延迟初始化检测器和格式化器（只初始化一次）
            if not hasattr(self, '_gmft_detector'):
                logger.info("initializing_gmft_models")
                self._gmft_detector = TableDetector()
                self._gmft_formatter = AutoTableFormatter()
                logger.info("gmft_models_initialized")
            
            tables_text = []
            doc = PyPDFium2Document(file_path)
            
            try:
                for page_idx, page in enumerate(doc):
                    # 检测表格
                    tables = self._gmft_detector.extract(page)
                    
                    for table_idx, table in enumerate(tables):
                        try:
                            # 格式化表格为DataFrame
                            ft = self._gmft_formatter.extract(table)
                            df = ft.df()
                            
                            # 过滤掉列数过多的"表格"（可能是误识别的流程图等）
                            if len(df.columns) > 10:
                                logger.debug("skipping_wide_table", page=page_idx+1, cols=len(df.columns))
                                continue
                            
                            # 过滤掉只有1行的表格（可能是误识别）
                            if len(df) < 2:
                                logger.debug("skipping_single_row_table", page=page_idx+1)
                                continue
                            
                            # 将DataFrame转换为文本格式
                            rows = []
                            # 添加表头
                            header = ' | '.join(str(col).replace('\n', ' ').strip() for col in df.columns)
                            rows.append(header)
                            
                            # 添加数据行
                            for _, row in df.iterrows():
                                cells = []
                                for val in row:
                                    if val is None or (isinstance(val, float) and str(val) == 'nan'):
                                        cells.append("")
                                    else:
                                        cells.append(str(val).replace('\n', ' ').strip())
                                rows.append(' | '.join(cells))
                            
                            table_text = '\n'.join(rows)
                            if table_text.strip():
                                tables_text.append(f"[表格 - 第{page_idx+1}页]\n{table_text}")
                                
                        except Exception as e:
                            logger.warning("gmft_table_format_error", page=page_idx+1, error=str(e))
                            continue
            finally:
                doc.close()
            
            if tables_text:
                logger.info("gmft_tables_extracted", table_count=len(tables_text))
            
            return tables_text
            
        except ImportError as e:
            logger.warning("gmft_not_installed_fallback_to_pdfplumber", error=str(e))
            return self._extract_tables_with_pdfplumber(file_path)
        except Exception as e:
            logger.warning("gmft_extraction_failed_fallback_to_pdfplumber", error=str(e))
            return self._extract_tables_with_pdfplumber(file_path)
    
    def _extract_tables_with_pdfplumber(self, file_path: str) -> List[str]:
        """使用 pdfplumber 从 PDF 中提取表格（备用方案）"""
        try:
            import pdfplumber
            
            tables_text = []
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()
                    for table_idx, table in enumerate(page_tables):
                        if not table:
                            continue
                        
                        # 将表格转换为文本格式
                        rows = []
                        for row in table:
                            # 清理单元格内容
                            cells = []
                            for cell in row:
                                if cell is None:
                                    cells.append("")
                                else:
                                    # 移除换行符，保持单元格内容在一行
                                    cells.append(str(cell).replace('\n', ' ').strip())
                            rows.append(' | '.join(cells))
                        
                        table_text = '\n'.join(rows)
                        if table_text.strip():
                            tables_text.append(f"[表格 - 第{page_num+1}页]\n{table_text}")
            
            if tables_text:
                logger.info("pdfplumber_tables_extracted", table_count=len(tables_text))
            
            return tables_text
            
        except Exception as e:
            logger.warning("pdfplumber_extraction_failed", error=str(e))
            return []

    def _pdf_to_images(self, file_path: str, scale: float = 2.0) -> List[tuple]:
        """
        将 PDF 每页转换为图片
        
        Args:
            file_path: PDF 文件路径
            scale: 缩放比例，默认 2x 以提高 OCR 精度
            
        Returns:
            [(page_num, image_bytes), ...] 列表
        """
        try:
            import fitz  # PyMuPDF
            
            images = []
            doc = fitz.open(file_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                # 缩放矩阵
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                images.append((page_num, img_bytes))
                
            doc.close()
            logger.info("pdf_converted_to_images", page_count=len(images), file_path=file_path)
            return images
            
        except Exception as e:
            logger.error("pdf_to_images_failed", error=str(e), file_path=file_path)
            raise

    # OCR 提示词（Qwen3-VL 通用多模态模型）
    OCR_PROMPT_DEFAULT = """识别图片中的所有文字，要求：
1. 按阅读顺序输出纯文本
2. 表格用markdown格式（| 列1 | 列2 |）
3. 不要添加```代码块标记
4. 不要添加页码或页眉页脚
5. 公式用LaTeX格式"""
    
    async def _call_ocr_api_single(
        self,
        image_bytes: bytes,
        page_num: int,
        prompt: str = None,
        max_retries: int = 3
    ) -> tuple:
        """
        调用 OCR API 处理单张图片（硅基流动 SiliconFlow - Qwen3-VL）
        
        Args:
            image_bytes: 图片字节数据
            page_num: 页码
            prompt: 提示词
            max_retries: 最大重试次数
            
        Returns:
            (page_num, extracted_text)
        """
        import httpx
        import base64
        import asyncio
        
        # 使用默认的 OCR 提示词
        if prompt is None:
            prompt = self.OCR_PROMPT_DEFAULT
        
        base64_image = base64.b64encode(image_bytes).decode()
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=float(self.OCR_TIMEOUT)) as client:
                    response = await client.post(
                        self.OCR_API_URL,
                        headers={
                            "Authorization": f"Bearer {self.OCR_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.OCR_MODEL,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                                        {"type": "text", "text": prompt}
                                    ]
                                }
                            ],
                            "max_tokens": 7000,
                            "enable_thinking": False  # 非思考模式
                        }
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    content = result["choices"][0]["message"]["content"]
                    # 清理可能的重复子串
                    content = self._clean_repeated_substrings(content)
                    
                    logger.debug("ocr_page_success", page_num=page_num, content_length=len(content))
                    return (page_num, content)
                    
            except httpx.ConnectError as e:
                logger.warning("ocr_connection_failed", page_num=page_num, error=str(e))
                return (page_num, f"[OCR失败: 连接错误 - 第{page_num + 1}页]")
            except httpx.TimeoutException as e:
                logger.warning("ocr_timeout", page_num=page_num, error=str(e))
                return (page_num, f"[OCR超时 - 第{page_num + 1}页]")
            except httpx.HTTPStatusError as e:
                error_body = e.response.text if e.response else "No response body"
                # 500 错误时重试
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning("ocr_server_error_retrying", page_num=page_num, attempt=attempt+1, status=e.response.status_code)
                    await asyncio.sleep(2 * (attempt + 1))  # 递增等待
                    continue
                logger.warning("ocr_http_error", page_num=page_num, status=e.response.status_code, error_body=error_body[:500])
                return (page_num, f"[OCR失败: HTTP {e.response.status_code} - 第{page_num + 1}页]")
            except Exception as e:
                logger.warning("ocr_failed", page_num=page_num, error=str(e), error_type=type(e).__name__)
                return (page_num, f"[OCR失败: {str(e)} - 第{page_num + 1}页]")
        
        return (page_num, f"[OCR失败: 重试{max_retries}次后仍失败 - 第{page_num + 1}页]")

    def _clean_repeated_substrings(self, text: str) -> str:
        """清理文本中的重复子串（HunyuanOCR 可能产生）"""
        n = len(text)
        if n < 8000:
            return text
            
        for length in range(2, n // 10 + 1):
            candidate = text[-length:]
            count = 0
            i = n - length
            
            while i >= 0 and text[i:i + length] == candidate:
                count += 1
                i -= length
                
            if count >= 10:
                return text[:n - length * (count - 1)]
                
        return text

    async def _process_pdf_with_ocr(self, file_path: str) -> str:
        """
        使用 DeepSeek-OCR 处理扫描件 PDF
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            提取的文本内容（Markdown 格式）
        """
        import asyncio
        
        # 1. PDF 转图片
        images = self._pdf_to_images(file_path)
        if not images:
            logger.warning("pdf_no_pages", file_path=file_path)
            return ""
        
        logger.info("ocr_starting", page_count=len(images), file_path=file_path)
        
        # 2. 使用信号量限制并发
        semaphore = asyncio.Semaphore(self.OCR_MAX_CONCURRENT)
        
        async def process_with_semaphore(page_num: int, img_bytes: bytes):
            async with semaphore:
                return await self._call_ocr_api_single(img_bytes, page_num)
        
        # 3. 并发调用 OCR
        tasks = [process_with_semaphore(page_num, img_bytes) for page_num, img_bytes in images]
        results = await asyncio.gather(*tasks)
        
        # 4. 按页码排序合并
        results.sort(key=lambda x: x[0])
        
        # 5. 合并文本，添加页码分隔
        content_parts = []
        for page_num, text in results:
            if text and not text.startswith("[OCR"):
                content_parts.append(f"<!-- 第{page_num + 1}页 -->\n{text}")
            elif text:
                content_parts.append(text)
        
        content = "\n\n".join(content_parts)
        
        logger.info(
            "ocr_completed",
            file_path=file_path,
            page_count=len(images),
            content_length=len(content)
        )
        
        return content

    def _get_unstructured(self):
        """延迟加载Unstructured"""
        if self._unstructured is None:
            from unstructured.partition.auto import partition
            self._unstructured = partition
        return self._unstructured

    def _get_embedding_model(self):
        """延迟加载Embedding模型（用于语义分块）"""
        if self._embedding_model is None:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            local_path = os.getenv("BGE_M3_MODEL_PATH")
            if local_path and os.path.exists(local_path):
                self._embedding_model = HuggingFaceEmbedding(model_name=local_path)
            else:
                self._embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3")

        return self._embedding_model

    def get_file_type(self, file_path: str) -> Optional[str]:
        """
        获取文件类型

        Args:
            file_path: 文件路径

        Returns:
            文件类型字符串，不支持则返回None
        """
        ext = Path(file_path).suffix.lower()
        return self.SUPPORTED_TYPES.get(ext)

    def is_supported(self, file_path: str) -> bool:
        """检查文件是否支持"""
        return self.get_file_type(file_path) is not None

    async def parse(self, file_path: str) -> str:
        """
        解析文档

        Args:
            file_path: 文件路径

        Returns:
            提取的文本内容

        Raises:
            ValueError: 文件类型不支持
            Exception: 解析失败
        """
        import asyncio
        
        if not self.is_supported(file_path):
            raise ValueError(f"Unsupported file type: {Path(file_path).suffix}")
        
        file_ext = Path(file_path).suffix.lower()
        
        # PDF 文件特殊处理：检测扫描件并使用 HunyuanOCR
        if file_ext == ".pdf":
            # 先尝试 fast 策略提取文本
            content, is_scanned = await asyncio.to_thread(self._try_fast_pdf_parse, file_path)
            
            if is_scanned:
                # 扫描件：使用 DeepSeek-OCR（硅基流动）
                logger.info("pdf_is_scanned_using_deepseek_ocr", file_path=file_path)
                content = await self._process_pdf_with_ocr(file_path)
            
            return content
        else:
            # 其他文件类型使用同步解析
            return await asyncio.to_thread(self._parse_sync, file_path)

    def _try_fast_pdf_parse(self, file_path: str) -> tuple:
        """
        尝试使用 fast 策略解析 PDF
        
        Returns:
            (content, is_scanned): 内容和是否为扫描件
        """
        partition = self._get_unstructured()
        
        try:
            # 使用 gmft 提取表格
            tables_text = self._extract_tables_with_gmft(file_path)
            
            # 使用 fast 策略提取文本
            elements = partition(
                filename=file_path,
                strategy="fast",
                include_page_breaks=False,
                languages=["chi_sim", "eng"]
            )
            
            # 检查是否提取到内容
            text_content = "".join(str(el) for el in elements).strip()
            
            if not text_content and not tables_text:
                # 没有文本也没有表格，是扫描件
                logger.info("pdf_detected_as_scanned", file_path=file_path)
                return ("", True)
            
            # 有内容，处理并返回
            if tables_text:
                from unstructured.documents.elements import Table
                for table_content in tables_text:
                    elements.append(Table(text=table_content))
            
            content = self._process_elements(elements)
            
            logger.info(
                "document_parsed",
                file_path=file_path,
                element_count=len(elements),
                content_length=len(content),
                table_count=content.count("[表格 - 第")
            )
            
            return (content, False)
            
        except Exception as e:
            logger.warning("fast_pdf_parse_failed", error=str(e), file_path=file_path)
            # 解析失败，当作扫描件处理
            return ("", True)

    def _parse_sync(self, file_path: str) -> str:
        """同步解析文档（非 PDF 文件）"""
        partition = self._get_unstructured()

        try:
            # 其他文件类型使用默认配置
            elements = partition(filename=file_path)
            content = self._process_elements(elements)
            
            logger.info(
                "document_parsed",
                file_path=file_path,
                element_count=len(elements),
                content_length=len(content)
            )

            return content

        except Exception as e:
            logger.error(
                "document_parse_failed",
                file_path=file_path,
                error=str(e)
            )
            raise

    def _process_elements(self, elements: list) -> str:
        """
        处理 Unstructured 提取的元素，转换为文本
        
        Args:
            elements: Unstructured 元素列表
            
        Returns:
            合并后的文本内容
        """
        content_parts = []
        for el in elements:
            el_type = type(el).__name__
            
            # 表格元素特殊处理
            if el_type == "Table":
                text = str(el).strip()
                # 只保留 gmft 提取的表格（以 "[表格 - 第" 开头）
                # 过滤掉 unstructured 提取的混乱表格文本
                if text.startswith("[表格 - 第"):
                    content_parts.append(text)
                # unstructured 识别的表格跳过
            else:
                text = str(el).strip()
                if text:
                    content_parts.append(text)

        return "\n\n".join(content_parts)

    async def chunk(
        self,
        content: str,
        strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        filename: str = "",
        llm_mode: str = "local"
    ) -> List[Dict[str, Any]]:
        """
        文档分块

        Args:
            content: 文档内容
            strategy: 分块策略 (llm/sentence/semantic/markdown/hybrid)
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠
            filename: 文件名（用于LLM分块的上下文生成）
            llm_mode: LLM模式 - "local"(本地千问3) / "online"(线上API)

        Returns:
            分块列表 [{"id": str, "content": str, "metadata": dict, ...}, ...]
        """
        import asyncio
        
        # LLM策略需要异步调用
        if strategy == "llm":
            return await self.chunk_with_llm(content, chunk_size, filename, llm_mode)
        
        # 其他策略在线程池中执行同步分块
        return await asyncio.to_thread(
            self._chunk_sync, content, strategy, chunk_size, chunk_overlap
        )

    def _chunk_sync(
        self,
        content: str,
        strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100
    ) -> List[Dict[str, Any]]:
        """同步分块（非LLM策略）"""
        if not content.strip():
            return []

        try:
            from llama_index.core.node_parser import SentenceSplitter
            from llama_index.core import Document

            doc = Document(text=content)

            # 选择分块策略
            if strategy == "semantic":
                parser = self._create_semantic_parser()
            elif strategy == "markdown":
                parser = self._create_markdown_parser()
            elif strategy == "hybrid":
                parser = self._create_hybrid_parser()
            else:  # sentence (默认)
                parser = SentenceSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )

            nodes = parser.get_nodes_from_documents([doc])

            # 转换为标准格式
            chunks = []
            for i, node in enumerate(nodes):
                chunks.append({
                    "id": f"chunk_{i}",
                    "content": node.text,
                    "metadata": node.metadata or {},
                    "start_char": getattr(node, "start_char_idx", None),
                    "end_char": getattr(node, "end_char_idx", None)
                })

            avg_size = sum(len(c["content"]) for c in chunks) / len(chunks) if chunks else 0

            logger.info(
                "document_chunked",
                strategy=strategy,
                chunk_count=len(chunks),
                avg_chunk_size=round(avg_size, 1)
            )

            return chunks

        except Exception as e:
            logger.error(
                "document_chunk_failed",
                strategy=strategy,
                error=str(e)
            )
            raise

    # LLM分块并发数
    LLM_CHUNK_MAX_CONCURRENT = int(os.getenv("LLM_CHUNK_MAX_CONCURRENT", "3"))

    async def chunk_with_llm(
        self,
        content: str,
        chunk_size: int = 512,
        filename: str = "",
        llm_mode: str = "local"
    ) -> List[Dict[str, Any]]:
        """
        使用LLM进行智能分块（支持本地/线上模式）

        Args:
            content: 文档内容
            chunk_size: 目标分块大小（字符数，仅作参考）
            filename: 文件名（用于生成上下文）
            llm_mode: LLM模式 - "local"(本地千问3) / "online"(线上API)

        Returns:
            分块列表（包含完整元数据）
        """
        if not content.strip():
            return []

        try:
            import asyncio
            
            # 根据模式选择配置
            is_online = llm_mode == "online"
            max_chars = LLM_CHUNK_MAX_CHARS_ONLINE if is_online else LLM_CHUNK_MAX_CHARS_LOCAL
            
            logger.info(
                "llm_chunking_started",
                llm_mode=llm_mode,
                max_chars=max_chars,
                content_length=len(content),
                filename=filename
            )
            
            # 判断是否需要分段
            needs_segmentation = len(content) > max_chars
            
            if needs_segmentation:
                # 需要分段：先生成文档上下文，再分段处理
                doc_context = await self._generate_doc_context_for_chunking(
                    content=content,
                    filename=filename,
                    llm_mode=llm_mode
                )
                
                segments = self._split_into_segments(content, max_chars)
                
                logger.info(
                    "document_segmented",
                    segment_count=len(segments),
                    doc_title=doc_context.get("title", "")
                )
                
                # 并发处理各segment
                semaphore = asyncio.Semaphore(self.LLM_CHUNK_MAX_CONCURRENT)
                
                async def process_segment(seg_idx: int, segment: str):
                    async with semaphore:
                        chunks = await self._llm_chunk_segment_with_context(
                            segment=segment,
                            chunk_size=chunk_size,
                            doc_context=doc_context,
                            segment_index=seg_idx,
                            total_segments=len(segments),
                            llm_mode=llm_mode
                        )
                        return (seg_idx, chunks)
                
                tasks = [process_segment(i, seg) for i, seg in enumerate(segments)]
                results = await asyncio.gather(*tasks)
                results.sort(key=lambda x: x[0])
                
                all_chunks = []
                for seg_idx, chunks in results:
                    for chunk in chunks:
                        chunk["id"] = f"chunk_{len(all_chunks)}"
                        chunk["metadata"]["segment_index"] = seg_idx
                        chunk["metadata"]["doc_context"] = doc_context
                        all_chunks.append(chunk)
            else:
                # 不需要分段：一次调用完成分块和上下文生成
                all_chunks = await self._llm_chunk_single_pass(
                    content=content,
                    chunk_size=chunk_size,
                    filename=filename,
                    llm_mode=llm_mode
                )

            # 添加上下文前缀增强（Contextual Chunking）
            all_chunks = self._enhance_chunks_with_context_prefix(all_chunks, filename)

            avg_size = sum(len(c["content"]) for c in all_chunks) / len(all_chunks) if all_chunks else 0

            logger.info(
                "document_chunked_with_llm",
                llm_mode=llm_mode,
                chunk_count=len(all_chunks),
                avg_chunk_size=round(avg_size, 1),
                needs_segmentation=needs_segmentation
            )

            return all_chunks

        except Exception as e:
            logger.error("llm_chunk_failed", error=str(e), llm_mode=llm_mode)
            logger.warning("falling_back_to_sentence_chunking")
            return self._chunk_sync(content, "sentence", chunk_size, chunk_size // 4)

    async def _llm_chunk_single_pass(
        self,
        content: str,
        chunk_size: int,
        filename: str,
        llm_mode: str
    ) -> List[Dict[str, Any]]:
        """
        单次LLM调用完成分块和上下文生成（文档较短时使用）
        
        优点：只调用1次LLM，效率高
        """
        import httpx
        
        content = self._preprocess_content(content)
        
        if self._is_toc_content(content):
            logger.info("skipping_toc_content", content_length=len(content))
            return []
        
        # 构建prompt：同时提取文档信息和分块
        prompt = f"""分析并分块以下文档，用于知识库检索。

## 文件名
{filename}

## 文档内容
{content}

        ## 任务
        1. 首先分析文档，提取标题、类型、主题等信息
        2. 然后按语义分块，每块500-1500字符

        ## 表格处理规则（重要）
如果识别到表格内容（即使格式混乱），必须：
1. 将表格整理成Markdown格式输出，如：
   | 污染物 | 限值(mg/m³) | 监测方法 |
   |--------|------------|---------|
   | SO2 | 50 | HJ/T 57 |
2. 表格前的说明文字（如"表1 排放限值"）与表格合并为一个chunk
        3. type字段标记为"table"
        4. 表头必须完整，不能遗漏列

        ## 输出要求（严格约束，务必遵守，否则系统将解析失败）
        你必须严格按照以下要求输出：
        1. 只输出一个完整的JSON对象，不要输出任何其他内容（包括思考过程、解释、Markdown代码块标记等）。
        2. 直接过滤掉目录和页眉页脚等无意义内容，只输出正文内容，对原文中明显存在错误的字符可以进行修正（可能是pdf文件解析错误导致）。
        3. 不要在JSON前或后添加任何文字说明。
        4. 不要在JSON中加入注释。
        5. 直接输出JSON，不要用```json```包裹。
        6. **必须输出“严格JSON”**：所有字符串必须符合JSON转义规则。
           - 字符串里的换行必须写成 \\n（不要输出真实换行到引号内部）。
           - 字符串里的反斜杠必须写成 \\\\（特别是出现公式/LaTeX时，如 \\mu、\\mathrm、\\text）。
           - 字符串里的英文双引号必须转义为 \\"，或改用中文引号/书名号，避免破坏JSON。
{{
    "doc_context": {{
        "title": "文档完整标题（如：广东省大气污染物排放限值 DB44/27-2001）",
        "doc_type": "文档类型（地方标准/国家标准/法律法规/技术规范/政策文件/研究报告）",
        "issuing_authority": "发布机构",
        "main_topics": ["主题1", "主题2"],
        "keywords": ["关键词1", "关键词2", "关键词3"]
    }},
    "chunks": [
        {{
            "content": "分块内容（表格必须整理成Markdown表格格式）",
            "topic": "具体主题（要体现文档名称，如：DB44/27-2001工业锅炉排放限值）",
            "type": "paragraph|table|list",
            "section": "所属章节（如：第三章 排放限值）"
        }}
    ]
}}"""

        try:
            result = await self._call_llm_api(prompt, llm_mode)

            # 调试：记录原始返回内容，便于分析JSON解析失败原因
            try:
                if LLM_CHUNK_LOG_FULL:
                    result_preview = result
                else:
                    preview_len = 400
                    result_preview = (result[:preview_len] + "...") if len(result) > preview_len else result
                logger.info(
                    "llm_single_pass_raw_result_preview",
                    preview=result_preview,
                    total_length=len(result),
                    llm_mode=llm_mode,
                    filename=filename,
                )
            except Exception:
                # 日志本身不能影响主流程
                pass

            # 改进的JSON提取逻辑：优先匹配最后一个完整的JSON对象，避免匹配到思考内容
            raw_json_text = None
            parsed = None
            
            # 辅助函数：尝试修复常见的JSON格式问题
            def fix_json_common_issues(text: str) -> str:
                """修复常见的JSON格式问题"""
                # 移除单行注释（// 注释）
                text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
                # 移除多行注释（/* 注释 */）
                text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
                # 移除尾随逗号（在 } 或 ] 之前）
                text = re.sub(r',(\s*[}\]])', r'\1', text)
                # 修复非法反斜杠转义（常见于LaTeX：\mu, \mathrm, \text 等）
                # JSON只允许 \" \\ \/ \b \f \n \r \t \uXXXX，其它如 \m 会导致 json.loads 失败
                # 这里将“不是合法JSON转义”的反斜杠补成双反斜杠：\mu -> \\mu
                text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
                return text.strip()
            
            # 策略1：尝试从后往前找最后一个完整的JSON对象（通常思考内容在前，JSON在后）
            json_candidates = list(re.finditer(r'\{[\s\S]*\}', result))
            if json_candidates:
                # 从最后一个候选开始尝试解析
                for candidate in reversed(json_candidates):
                    candidate_text = candidate.group()
                    # 检查是否包含预期的字段（提高准确性）
                    if '"doc_context"' in candidate_text and '"chunks"' in candidate_text:
                        # 先尝试直接解析
                        try:
                            parsed = json.loads(candidate_text)
                            raw_json_text = candidate_text
                            logger.debug("llm_json_extracted_from_last_candidate", candidate_index=len(json_candidates) - json_candidates.index(candidate))
                            break
                        except json.JSONDecodeError as e:
                            # 尝试修复后解析
                            try:
                                fixed_text = fix_json_common_issues(candidate_text)
                                parsed = json.loads(fixed_text)
                                raw_json_text = fixed_text
                                logger.debug("llm_json_extracted_from_last_candidate_fixed", candidate_index=len(json_candidates) - json_candidates.index(candidate))
                                break
                            except json.JSONDecodeError:
                                continue
            
            # 策略2：如果策略1失败，尝试所有候选，找到第一个能成功解析的
            if parsed is None and json_candidates:
                for candidate in json_candidates:
                    candidate_text = candidate.group()
                    # 先尝试直接解析
                    try:
                        test_parsed = json.loads(candidate_text)
                        # 验证结构是否符合预期
                        if isinstance(test_parsed, dict) and "doc_context" in test_parsed and "chunks" in test_parsed:
                            parsed = test_parsed
                            raw_json_text = candidate_text
                            logger.debug("llm_json_extracted_from_fallback_candidate")
                            break
                    except json.JSONDecodeError:
                        # 尝试修复后解析
                        try:
                            fixed_text = fix_json_common_issues(candidate_text)
                            test_parsed = json.loads(fixed_text)
                            if isinstance(test_parsed, dict) and "doc_context" in test_parsed and "chunks" in test_parsed:
                                parsed = test_parsed
                                raw_json_text = fixed_text
                                logger.debug("llm_json_extracted_from_fallback_candidate_fixed")
                                break
                        except json.JSONDecodeError:
                            continue
            
            # 如果仍然失败，记录详细的调试信息
            if parsed is None:
                # 记录所有候选的片段和错误信息
                error_details = []
                for i, candidate in enumerate(json_candidates[:5]):  # 只记录前5个候选
                    candidate_text = candidate.group()
                    error_details.append({
                        "index": i,
                        "length": len(candidate_text),
                        "preview": candidate_text[:200] + "..." if len(candidate_text) > 200 else candidate_text,
                        "has_doc_context": '"doc_context"' in candidate_text,
                        "has_chunks": '"chunks"' in candidate_text
                    })
                
                logger.error(
                    "llm_json_parse_failed_detailed",
                    total_candidates=len(json_candidates),
                    result_length=len(result),
                    result_preview=result[:500] + "..." if len(result) > 500 else result,
                    candidates_preview=error_details
                )
                raise ValueError("LLM返回结果无法解析为JSON，请重试")
            
            # 记录提取到的JSON片段（用于调试）
            try:
                logger.info(
                    "llm_single_pass_json_snippet",
                    snippet=raw_json_text if LLM_CHUNK_LOG_FULL else ((raw_json_text[:400] + "...") if len(raw_json_text) > 400 else raw_json_text),
                    snippet_length=len(raw_json_text),
                )
            except Exception:
                pass
            doc_context = parsed.get("doc_context", {})
            doc_context["filename"] = filename
            
            chunks = []
            for i, item in enumerate(parsed.get("chunks", [])):
                chunk_content = item.get("content", "").strip()
                if chunk_content:
                    chunks.append({
                        "id": f"chunk_{i}",
                        "content": chunk_content,
                        "original_content": chunk_content,
                        "metadata": {
                            "topic": item.get("topic", ""),
                            "type": item.get("type", "paragraph"),
                            "section": item.get("section", ""),
                            "doc_context": doc_context,
                            "chunking_method": f"llm_{llm_mode}_single_pass"
                        },
                        "start_char": None,
                        "end_char": None
                    })
            
            chunks = self._merge_small_chunks(chunks, min_size=150)
            if not chunks:
                raise ValueError("LLM分块结果为空，请重试")
            return chunks
            
        except Exception as e:
            logger.error(
                "llm_single_pass_failed",
                error=str(e),
                llm_mode=llm_mode,
                filename=filename,
            )
            raise RuntimeError(f"LLM分块失败: {str(e)}")

    async def _generate_doc_context_for_chunking(
        self,
        content: str,
        filename: str,
        llm_mode: str
    ) -> Dict[str, Any]:
        """
        生成文档级上下文（用于多segment分块场景）
        """
        # 取开头3000字符 + 结尾1000字符
        head = content[:3000]
        tail = content[-1000:] if len(content) > 4000 else ""
        sample = f"{head}\n...(中间省略)...\n{tail}" if tail else head
        
        prompt = f"""分析以下文档，提取关键信息用于后续分块。

文件名: {filename}

文档内容（开头和结尾）:
{sample}

## 输出要求（严格约束，务必遵守，否则系统将解析失败）
1. 只输出一个完整的JSON对象，不要输出任何其他内容（包括解释、思考过程、Markdown代码块标记等）。
2. 不要在JSON前或后添加任何文字说明。
3. 不要在JSON中加入注释。
4. 直接输出JSON，不要用```json```包裹。
5. 必须输出严格JSON：字符串中的英文双引号请使用 \\" 转义；反斜杠请使用 \\\\；不要在引号内部输出真实换行（如有需要用 \\n）。

请用JSON格式返回：
{{
    "title": "文档完整标题（如：广东省大气污染物排放限值 DB44/27-2001）",
    "doc_type": "文档类型（地方标准/国家标准/法律法规/技术规范/政策文件/研究报告/其他）",
    "issuing_authority": "发布机构（如有）",
    "main_topics": ["主题1", "主题2", "主题3"],
    "structure_hint": "文档结构说明（如：按章节组织/按附录组织/按污染物分类）",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}"""

        try:
            result = await self._call_llm_api(prompt, llm_mode)
            
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                doc_context = json.loads(json_match.group())
                doc_context["filename"] = filename
                return doc_context
                
        except Exception as e:
            logger.warning("generate_doc_context_failed", error=str(e))
        
        return {
            "filename": filename,
            "title": Path(filename).stem if filename else "",
            "doc_type": "",
            "main_topics": [],
            "keywords": []
        }

    async def _llm_chunk_segment_with_context(
        self,
        segment: str,
        chunk_size: int,
        doc_context: Dict[str, Any],
        segment_index: int,
        total_segments: int,
        llm_mode: str
    ) -> List[Dict[str, Any]]:
        """
        对单个segment进行分块（携带文档级上下文）
        """
        segment = self._preprocess_content(segment)
        
        if self._is_toc_content(segment):
            return []
        
        # 构建文档上下文提示
        doc_title = doc_context.get("title", "")
        doc_type = doc_context.get("doc_type", "")
        main_topics = ", ".join(doc_context.get("main_topics", []))
        keywords = ", ".join(doc_context.get("keywords", []))
        
        context_hint = f"""## 文档信息（重要！请在生成topic时参考）
- 文档标题: {doc_title}
- 文档类型: {doc_type}
- 主要主题: {main_topics}
- 关键词: {keywords}
- 当前位置: 第{segment_index + 1}部分，共{total_segments}部分
"""

        prompt = f"""{context_hint}

## 任务
将以下文档片段按语义分块，用于知识库检索。

## 规则
1. 分块大小：500-1500字符，宁大勿小
2. 跳过：纯目录、页眉页脚、版权声明
3. topic要具体：结合文档信息，写明"某某法/标准的某某条款"
4. 列表/步骤保持完整
5. 避免重复：本段只覆盖“当前片段”内容；不要重复输出前一段/后一段已出现的整段内容（允许少量承接句用于语义完整）。

## 表格处理规则（重要）
如果识别到表格内容（即使OCR后格式混乱），必须：
1. 整理成Markdown表格格式，如：
   | 污染物 | 限值 | 单位 |
   |--------|------|------|
   | SO2 | 50 | mg/m³ |
2. 表格前的说明（如"表1 排放限值"）与表格合并为一个chunk
3. type标记为"table"
4. 表头必须完整，不能遗漏

## 输出要求（严格约束，务必遵守，否则系统将解析失败）
1. 只输出一个完整JSON对象，不要输出任何其他内容（包括解释、思考过程、Markdown代码块标记等）。
2. 不要在JSON前或后添加任何文字说明。
3. 不要在JSON中加入注释。
4. 直接输出JSON，不要用```json```包裹。
5. 必须输出严格JSON：字符串中的英文双引号请使用 \\" 转义；反斜杠请使用 \\\\（尤其是公式/LaTeX：\\\\mu、\\\\mathrm、\\\\text）；不要在引号内部输出真实换行（如有需要用 \\n）。

## 输出JSON（只需要输出chunks，不要输出doc_context）
{{"chunks":[{{"content":"完整内容（表格整理成Markdown格式）","topic":"具体主题","type":"paragraph|table|list","section":"章节"}}]}}

## 文档片段
{segment}"""

        try:
            result = await self._call_llm_api(prompt, llm_mode)
            
            json_match = re.search(r'\{[\s\S]*\}', result)
            if not json_match:
                raise ValueError(f"LLM返回结果无法解析为JSON（segment {segment_index + 1}），请重试")
            
            parsed = json.loads(json_match.group())
            
            chunks = []
            for i, item in enumerate(parsed.get("chunks", [])):
                chunk_content = item.get("content", "").strip()
                if chunk_content and len(chunk_content) >= 100:
                    chunks.append({
                        "id": f"chunk_{i}",
                        "content": chunk_content,
                        "metadata": {
                            "topic": item.get("topic", ""),
                            "type": item.get("type", "paragraph"),
                            "section": item.get("section", ""),
                            "chunking_method": f"llm_{llm_mode}_contextual"
                        },
                        "start_char": None,
                        "end_char": None
                    })
            
            if not chunks:
                raise ValueError(f"LLM分块结果为空（segment {segment_index + 1}），请重试")
            return self._merge_small_chunks(chunks, min_size=150)
            
        except Exception as e:
            logger.error("llm_chunk_segment_failed", error=str(e), segment_index=segment_index)
            raise RuntimeError(f"LLM分块失败（segment {segment_index + 1}）: {str(e)}")

    async def _call_llm_api(self, prompt: str, llm_mode: str) -> str:
        """
        统一的LLM API调用接口
        
        Args:
            prompt: 提示词
            llm_mode: "local" 或 "online"
            
        Returns:
            LLM响应文本
        """
        import httpx
        
        if llm_mode == "online":
            return await self._call_online_llm(prompt)
        else:
            return await self._call_local_llm(prompt)

    async def _call_local_llm(self, prompt: str) -> str:
        """调用本地千问3，带重试机制"""
        import httpx
        import asyncio

        base_url = os.getenv("QWEN_BASE_URL")
        model = os.getenv("QWEN_MODEL", "qwen3")

        if not base_url:
            raise ValueError("QWEN_BASE_URL not configured in .env")

        # 重试配置：最多重试1次（总共2次尝试）
        max_retries = 2
        base_delay = 2

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "你是文档分析助手。直接返回JSON，不要解释。"},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.1
                        }
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    if attempt > 0:
                        logger.info("local_llm_retry_success", attempt=attempt + 1)
                    return result["choices"][0]["message"]["content"]
                    
            except httpx.HTTPStatusError as e:
                is_retryable = e.response.status_code in [429, 500, 502, 503, 504]
                is_last_attempt = attempt == max_retries - 1
                
                if is_retryable and not is_last_attempt:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "local_llm_http_error_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        status_code=e.response.status_code,
                        retry_delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "local_llm_http_error_final",
                        attempt=attempt + 1,
                        status_code=e.response.status_code
                    )
                    raise
                    
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                is_last_attempt = attempt == max_retries - 1
                
                if not is_last_attempt:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "local_llm_network_error_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error_type=type(e).__name__,
                        retry_delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "local_llm_network_error_final",
                        attempt=attempt + 1,
                        error_type=type(e).__name__
                    )
                    raise
                    
            except Exception as e:
                logger.error(
                    "local_llm_unexpected_error",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
        
        raise RuntimeError(f"本地LLM调用失败，已尝试{max_retries}次")

    async def _call_online_llm(self, prompt: str) -> str:
        """调用线上LLM API（DeepSeek/MiniMax/OpenAI/Mimo），带重试机制"""
        import httpx
        import asyncio
        
        provider = ONLINE_LLM_PROVIDER.lower()
        
        if provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        elif provider == "minimax":
            api_key = os.getenv("MINIMAX_API_KEY")
            base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
            model = os.getenv("MINIMAX_MODEL", "abab6.5s-chat")
        elif provider == "mimo":
            api_key = os.getenv("MIMO_API_KEY")
            base_url = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
            model = os.getenv("MIMO_MODEL", "mimo-v2-flash")
        else:  # openai
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        
        if not api_key:
            raise ValueError(f"API key not configured for provider: {provider}")
        
        # 重试配置：最多重试1次（总共2次尝试）
        max_retries = 2
        base_delay = 2  # 基础延迟（秒）
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    # 构建请求体
                    request_body = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "你是文档分析助手。直接返回JSON，不要解释。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1
                    }
                    
                    # MiniMax API: 禁用思考模式
                    if provider == "minimax":
                        request_body["reasoning_split"] = False
                    
                    # Xiaomi Mimo API: 禁用思考模式
                    if provider == "mimo":
                        request_body["extra_body"] = {"thinking": {"type": "disabled"}}
                    
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}"
                        },
                        json=request_body
                    )
                    response.raise_for_status()
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    # 防御性过滤：移除可能的思考内容标记
                    thinking_patterns = [
                        r'<think>.*?</think>',
                        r'<thinking>.*?</thinking>',
                        r'<reasoning>.*?</reasoning>',
                        r'<thought>.*?</thought>',
                    ]
                    for pattern in thinking_patterns:
                        content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
                    
                    # 成功则返回
                    if attempt > 0:
                        logger.info("llm_api_retry_success", attempt=attempt + 1, provider=provider)
                    return content
                    
            except httpx.HTTPStatusError as e:
                # HTTP 错误：429 限流、5xx 服务端错误等
                is_retryable = e.response.status_code in [429, 500, 502, 503, 504]
                is_last_attempt = attempt == max_retries - 1
                
                if is_retryable and not is_last_attempt:
                    delay = base_delay * (2 ** attempt)  # 指数退避：2s, 4s, 8s
                    logger.warning(
                        "llm_api_http_error_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        status_code=e.response.status_code,
                        provider=provider,
                        retry_delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 不可重试的错误或最后一次尝试失败
                    logger.error(
                        "llm_api_http_error_final",
                        attempt=attempt + 1,
                        status_code=e.response.status_code,
                        provider=provider
                    )
                    raise
                    
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                # 网络错误、超时等
                is_last_attempt = attempt == max_retries - 1
                
                if not is_last_attempt:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "llm_api_network_error_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error_type=type(e).__name__,
                        provider=provider,
                        retry_delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "llm_api_network_error_final",
                        attempt=attempt + 1,
                        error_type=type(e).__name__,
                        provider=provider
                    )
                    raise
                    
            except Exception as e:
                # 其他未预期错误，不重试
                logger.error(
                    "llm_api_unexpected_error",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                    provider=provider
                )
                raise
        
        # 理论上不会到这里，但保险起见
        raise RuntimeError(f"LLM API调用失败，已尝试{max_retries}次")

    def _enhance_chunks_with_context_prefix(
        self,
        chunks: List[Dict[str, Any]],
        filename: str
    ) -> List[Dict[str, Any]]:
        """
        为分块添加上下文前缀（Contextual Chunking）
        """
        enhanced_chunks = []
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc_context = metadata.get("doc_context", {})
            
            # 构建上下文前缀
            context_parts = []
            
            # 文档标题
            title = doc_context.get("title", "") or Path(filename).stem if filename else ""
            if title:
                context_parts.append(f"来源: {title}")
            
            # 主题
            topic = metadata.get("topic", "")
            if topic:
                context_parts.append(f"主题: {topic}")
            
            # 章节
            section = metadata.get("section", "")
            if section:
                context_parts.append(f"章节: {section}")
            
            # 类型
            type_map = {"paragraph": "正文", "table": "表格", "list": "列表"}
            chunk_type = metadata.get("type", "paragraph")
            context_parts.append(f"类型: {type_map.get(chunk_type, chunk_type)}")
            
            # 构建增强后的chunk：content保持原文，embedding_text用于检索增强
            original_content = chunk.get("original_content") or chunk.get("content", "")
            enhanced_chunk = chunk.copy()
            enhanced_chunk["content"] = original_content
            enhanced_chunk["original_content"] = original_content

            if context_parts:
                context_prefix = f"[{' | '.join(context_parts)}]\n"
                enhanced_chunk["context_prefix"] = context_prefix
                enhanced_chunk["embedding_text"] = context_prefix + original_content
            else:
                enhanced_chunk["context_prefix"] = ""
                enhanced_chunk["embedding_text"] = original_content

            enhanced_chunks.append(enhanced_chunk)
        
        return enhanced_chunks

    def _preprocess_content(self, content: str) -> str:
        """预处理文档内容，清理无关格式标记"""
        import re
        
        # 统一换行并移除控制字符
        content = content.replace("\r", "")
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', content)
        # 去掉不间断空格
        content = content.replace("\u00a0", " ")

        # 预防LLM直接照抄反斜杠导致JSON非法：先把反斜杠双写
        content = content.replace("\\", "\\\\")

        # 移除页码标记: <!-- 第N页 -->
        content = re.sub(r'<!--\s*第\d+页\s*-->', '', content)
        
        # 移除markdown代码块标记
        content = re.sub(r'```(?:text|markdown|latex)?\s*', '', content)
        
        # 移除单独的页码行 (如 "- 2 -", "第3页", "Page 5")
        content = re.sub(r'^\s*[-—]\s*\d+\s*[-—]\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*第\s*\d+\s*页\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*Page\s*\d+\s*$', '', content, flags=re.MULTILINE | re.IGNORECASE)
        
        # 移除连续空行（保留最多一个空行）
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content.strip()

    def _is_toc_content(self, content: str) -> bool:
        """检测是否为目录内容"""
        # 目录特征：大量的 "..." 或页码引用
        dot_pattern = r'\.{3,}'
        page_ref_pattern = r'\d+\s*$'
        
        lines = content.strip().split('\n')
        if len(lines) < 3:
            return False
        
        toc_line_count = 0
        for line in lines:
            if re.search(dot_pattern, line) or re.search(page_ref_pattern, line.strip()):
                toc_line_count += 1
        
        # 超过60%的行符合目录特征
        return toc_line_count / len(lines) > 0.6

    async def _llm_chunk_segment(
        self,
        proxy_url: str,
        content: str,
        chunk_size: int
    ) -> List[Dict[str, Any]]:
        """对单个片段调用本地千问3进行分块"""
        import httpx
        
        # 预处理：清理格式标记
        content = self._preprocess_content(content)
        
        # 检测并跳过目录
        if self._is_toc_content(content):
            logger.info("skipping_toc_content", content_length=len(content))
            return []
        
        # 优化后的提示词
        prompt = f"""将文档按语义分块，用于知识库检索。

## 规则
1. 分块大小：500-1500字符，宁大勿小
2. 跳过：纯目录、页眉页脚、版权声明
3. 公文格式：发文头(文号+标题+单位)合并，各附件独立
4. 列表/步骤保持完整，不要拆散

## 表格处理规则（重要）
如果识别到表格内容（即使OCR后格式混乱），必须：
1. 整理成Markdown表格格式，如：
   | 污染物 | 限值 | 单位 |
   |--------|------|------|
   | SO2 | 50 | mg/m³ |
2. 表格前的说明（如"表1 排放限值"）与表格合并
3. type标记为"table"

## 输出JSON
{{"chunks":[{{"content":"完整内容（表格整理成Markdown格式）","topic":"主题","type":"paragraph|table|list"}}]}}

## 文档
{content}"""

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    proxy_url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": "qwen3",
                        "messages": [
                            {"role": "system", "content": "你是文档分块助手。直接返回JSON，不要解释。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1
                    }
                )
                response.raise_for_status()
                result = response.json()

            result_text = result["choices"][0]["message"]["content"]
            
            # 提取JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                logger.warning("llm_response_no_json_found")
                return self._fallback_chunk(content, chunk_size)

            chunks = []
            for i, item in enumerate(parsed.get("chunks", [])):
                chunk_content = item.get("content", "").strip()
                # 过滤过小的块（小于100字符可能是噪音）
                if chunk_content and len(chunk_content) >= 100:
                    chunks.append({
                        "id": f"chunk_{i}",
                        "content": chunk_content,
                        "metadata": {
                            "topic": item.get("topic", ""),
                            "type": item.get("type", "paragraph"),
                            "chunking_method": "llm_qwen3"
                        },
                        "start_char": None,
                        "end_char": None
                    })
            
            # 合并过小的块
            chunks = self._merge_small_chunks(chunks, min_size=150)

            if not chunks:
                raise ValueError("LLM分块结果为空，请重试")
            return chunks

        except json.JSONDecodeError as e:
            logger.error("llm_response_parse_failed", error=str(e))
            raise RuntimeError(f"LLM返回结果解析失败: {str(e)}")
        except httpx.ConnectError as e:
            logger.error("llm_proxy_connection_failed", error=str(e), proxy_url=proxy_url)
            raise RuntimeError(f"LLM服务连接失败: {str(e)}")
        except httpx.TimeoutException as e:
            logger.error("llm_proxy_timeout", error=str(e), proxy_url=proxy_url)
            raise RuntimeError(f"LLM服务超时: {str(e)}")
        except Exception as e:
            logger.error("llm_chunk_segment_failed", error=str(e), error_type=type(e).__name__)
            raise RuntimeError(f"LLM分块失败: {str(e)}")

    def _merge_small_chunks(self, chunks: List[Dict[str, Any]], min_size: int = 150) -> List[Dict[str, Any]]:
        """合并过小的分块"""
        if not chunks:
            return chunks
        
        merged = []
        buffer = None
        
        for chunk in chunks:
            content_len = len(chunk.get("content", ""))
            
            if content_len < min_size:
                if buffer:
                    # 合并到buffer
                    buffer["content"] += "\n\n" + chunk["content"]
                    buffer["original_content"] = buffer["content"]
                    # 合并topic
                    if chunk.get("metadata", {}).get("topic"):
                        existing_topic = buffer.get("metadata", {}).get("topic", "")
                        new_topic = chunk["metadata"]["topic"]
                        if existing_topic and new_topic not in existing_topic:
                            buffer["metadata"]["topic"] = f"{existing_topic}; {new_topic}"
                else:
                    buffer = chunk.copy()
            else:
                if buffer:
                    # 先检查buffer是否足够大
                    if len(buffer.get("content", "")) >= min_size:
                        merged.append(buffer)
                    else:
                        # buffer太小，合并到当前chunk
                        chunk["content"] = buffer["content"] + "\n\n" + chunk["content"]
                        chunk["original_content"] = chunk["content"]
                    buffer = None
                merged.append(chunk)
        
        # 处理剩余的buffer
        if buffer:
            if merged and len(buffer.get("content", "")) < min_size:
                # 合并到最后一个chunk
                merged[-1]["content"] += "\n\n" + buffer["content"]
                merged[-1]["original_content"] = merged[-1]["content"]
            else:
                merged.append(buffer)
        
        return merged

    def _split_into_segments(self, content: str, max_chars: int) -> List[str]:
        """将长文档预分割成较小的片段"""
        segments = []
        
        # 先按双换行分割成段落
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_segment = ""
        for para in paragraphs:
            # 表格内容（以[表格开头）尽量保持完整
            is_table = para.strip().startswith("[表格")
            if len(current_segment) + len(para) + 2 <= max_chars:
                current_segment += para + "\n\n"
            else:
                if current_segment.strip():
                    segments.append(current_segment.strip())
                # 表格内容即使超长也尽量保持完整（不按句子切分）
                if is_table:
                    # 表格直接作为一个段落，即使超长
                    if len(para) > max_chars:
                        # 如果表格实在太长，单独作为一个segment
                        segments.append(para.strip())
                        current_segment = ""
                    else:
                        current_segment = para + "\n\n"
                # 如果单个段落超长，强制按句子切分
                elif len(para) > max_chars:
                    sentences = re.split(r'([。！？.!?])', para)
                    sub_segment = ""
                    for i in range(0, len(sentences), 2):
                        sent = sentences[i]
                        if i + 1 < len(sentences):
                            sent += sentences[i + 1]
                        if len(sub_segment) + len(sent) <= max_chars:
                            sub_segment += sent
                        else:
                            if sub_segment.strip():
                                segments.append(sub_segment.strip())
                            sub_segment = sent
                    if sub_segment.strip():
                        current_segment = sub_segment + "\n\n"
                    else:
                        current_segment = ""
                else:
                    current_segment = para + "\n\n"
        
        if current_segment.strip():
            segments.append(current_segment.strip())
        
        return segments if segments else [content]

    def _fallback_chunk(self, content: str, chunk_size: int) -> List[Dict[str, Any]]:
        """降级分块方法"""
        chunks = []
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append({
                        "id": f"chunk_{len(chunks)}",
                        "content": current_chunk.strip(),
                        "metadata": {"chunking_method": "fallback"},
                        "start_char": None,
                        "end_char": None
                    })
                current_chunk = para + "\n\n"
        
        if current_chunk.strip():
            chunks.append({
                "id": f"chunk_{len(chunks)}",
                "content": current_chunk.strip(),
                "metadata": {"chunking_method": "fallback"},
                "start_char": None,
                "end_char": None
            })
        
        return chunks

    def _create_semantic_parser(self):
        """创建语义分块解析器"""
        from llama_index.core.node_parser import SemanticSplitterNodeParser

        embed_model = self._get_embedding_model()
        return SemanticSplitterNodeParser(
            embed_model=embed_model,
            buffer_size=1,
            breakpoint_percentile_threshold=95
        )

    def _create_markdown_parser(self):
        """创建Markdown分块解析器"""
        from llama_index.core.node_parser import MarkdownNodeParser
        return MarkdownNodeParser()

    def _create_hybrid_parser(self):
        """创建混合分块解析器"""
        from llama_index.core.node_parser import HierarchicalNodeParser
        return HierarchicalNodeParser.from_defaults(
            chunk_sizes=[1024, 256, 64]
        )

    async def parse_and_chunk(
        self,
        file_path: str,
        strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100
    ) -> Dict[str, Any]:
        """
        解析并分块文档（便捷方法）

        Args:
            file_path: 文件路径
            strategy: 分块策略
            chunk_size: 分块大小
            chunk_overlap: 分块重叠

        Returns:
            {
                "content": str,          # 原始内容
                "chunks": List[Dict],    # 分块列表
                "file_type": str,        # 文件类型
                "chunk_count": int       # 分块数量
            }
        """
        # 解析
        content = await self.parse(file_path)

        # 分块
        chunks = await self.chunk(
            content=content,
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        return {
            "content": content,
            "chunks": chunks,
            "file_type": self.get_file_type(file_path),
            "chunk_count": len(chunks)
        }
