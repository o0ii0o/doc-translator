"""Markdown 文件读取"""

from pathlib import Path

from src.infra.logging import get_logger

logger = get_logger("markdown_parser")


class MarkdownParser:
    """读取 Markdown 文件并保留格式"""

    def read(self, md_path: Path) -> str:
        """读取 Markdown 文件内容"""
        md_path = Path(md_path)

        if not md_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {md_path}")

        logger.info("读取 Markdown: %s", md_path.name)
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        logger.debug("读取完成，%d 字符", len(content))
        return content
