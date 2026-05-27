"""文件处理器 - 检测文件类型并路由到对应处理器"""

from pathlib import Path
from typing import Optional

from .logger import get_logger
from .pdf_parser import PDFParser
from .md_reader import MarkdownReader

logger = get_logger("file_handler")


class FileHandler:
    """统一文件处理入口"""

    SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown"}

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.pdf_parser = PDFParser(config_path)
        self.md_reader = MarkdownReader()

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
            content = self.md_reader.read(file_path)
            logger.info("Markdown 读取完成，%d 字符", len(content))

        return content
