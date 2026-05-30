"""Markdown 文本切分"""

import re
from pathlib import Path
from typing import Optional

from src.core.models.chunk import Chunk
from src.infra.config import load_config
from src.infra.logging import get_logger

logger = get_logger("chunking")


class MarkdownChunker:
    """将 Markdown 切分为可独立处理的文本块"""

    def __init__(self, max_size: int = 4000, config_path: Optional[Path] = None):
        if config_path:
            config = load_config(config_path)
            translation_cfg = config.get("translation", {})
            max_size = translation_cfg.get("batch_size", max_size)
        self.max_size = max_size

    def split(self, content: str) -> list[Chunk]:
        """切分文本并返回 Chunk 列表（过滤空段）"""
        if len(content) <= self.max_size:
            if not content.strip():
                return []
            return [Chunk(index=0, text=content)]

        raw_sections = self._split_into_sections(content)
        non_empty = [s for s in raw_sections if s.strip()]

        chunks = [
            Chunk(index=i, text=text) for i, text in enumerate(non_empty)
        ]

        if len(non_empty) < len(raw_sections):
            logger.debug(
                "已过滤 %d 个空段",
                len(raw_sections) - len(non_empty),
            )

        logger.info("内容已分为 %d 段", len(chunks))
        return chunks

    def _split_into_sections(self, content: str) -> list[str]:
        """按 Markdown 标题分割内容"""
        sections = []
        current_section = []

        lines = content.split("\n")
        for line in lines:
            if re.match(r"^#{1,6}\s+", line) and current_section:
                sections.append("\n".join(current_section))
                current_section = []

            current_section.append(line)

        if current_section:
            sections.append("\n".join(current_section))

        merged = []
        for section in sections:
            if len(section) <= self.max_size:
                merged.append(section)
            else:
                sub = self._split_by_length(section)
                logger.debug("章节过长，按长度拆分为 %d 段", len(sub))
                merged.extend(sub)

        return merged

    def _split_by_length(self, text: str) -> list[str]:
        """按长度分割文本"""
        chunks = []
        current = []

        for line in text.split("\n"):
            current.append(line)
            if sum(len(c) for c in current) >= self.max_size:
                chunks.append("\n".join(current))
                current = []

        if current:
            chunks.append("\n".join(current))

        return chunks
