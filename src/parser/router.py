"""文档解析路由 - 按文件类型分发到对应解析器"""

from pathlib import Path
from typing import Optional

from src.infra.logging import get_logger
from src.parser.markdown_parser import MarkdownParser
from src.parser.pdf_parser import PDFParser

logger = get_logger("parser")


class DocumentRouter:
    """统一文档解析入口"""

    SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown"}

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self._pdf_parser: Optional[PDFParser] = None
        self.markdown_parser = MarkdownParser()

    @property
    def pdf_parser(self) -> PDFParser:
        if self._pdf_parser is None:
            self._pdf_parser = PDFParser(self.config_path)
        return self._pdf_parser

    def process(self, file_path: Path, *, force_parse: bool = False) -> str:
        """处理文件并返回 Markdown 内容"""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = file_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"不支持的文件类型: {ext}。支持的类型: {self.SUPPORTED_EXTENSIONS}"
            )

        logger.info("检测到文件类型: %s", ext)

        if ext == ".pdf":
            content = self.pdf_parser.parse(file_path, force=force_parse)
            logger.info("PDF 内容就绪，%d 字符", len(content))
        else:
            content = self.markdown_parser.read(file_path)
            logger.info("Markdown 读取完成，%d 字符", len(content))

        return content
