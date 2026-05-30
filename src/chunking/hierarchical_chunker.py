"""层次切片 - Section + Leaf 两层结构，供 RAG 索引用"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.models.index_chunk import IndexChunk
from src.infra.config import load_config
from src.infra.logging import get_logger

logger = get_logger("chunking")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")
_IMAGE_ONLY_RE = re.compile(r"^!\[.*\]\(.*\)\s*$")


@dataclass
class _Section:
    heading_path: list[str]
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


class HierarchicalChunker:
    """按 Markdown 标题层次切分为 section（父）与 leaf（子，用于 embedding）"""

    def __init__(self, config_path: Optional[Path] = None):
        config = load_config(config_path)
        index_cfg = config.get("index", {})
        self.section_heading_levels = set(
            index_cfg.get("section_heading_levels", [1, 2])
        )
        self.leaf_target_size = index_cfg.get("leaf_target_size", 700)
        self.leaf_overlap = index_cfg.get("leaf_overlap", 100)
        self.min_leaf_size = index_cfg.get("min_leaf_size", 80)
        self.prefix_heading_in_leaf = index_cfg.get(
            "prefix_heading_in_leaf", True
        )

    def split(
        self, content: str, doc_id: str, lang: str = ""
    ) -> list[IndexChunk]:
        """将 Markdown 切分为 section 与 leaf 节点列表"""
        sections = self._parse_sections(content)
        if not sections:
            if not content.strip():
                return []
            sections = [_Section(heading_path=[], lines=content.split("\n"))]

        chunks: list[IndexChunk] = []
        sec_idx = 0
        leaf_idx = 0

        for section in sections:
            section_text = section.text
            if not section_text or self._is_noise(section_text):
                continue

            section_id = f"{doc_id}:sec:{sec_idx}"
            chunks.append(
                IndexChunk(
                    chunk_id=section_id,
                    doc_id=doc_id,
                    parent_id=None,
                    level="section",
                    index=sec_idx,
                    text=section_text,
                    heading_path=list(section.heading_path),
                    lang=lang,
                )
            )

            leaves = self._section_to_leaves(section, doc_id, section_id, lang)
            for leaf in leaves:
                leaf.index = leaf_idx
                leaf.chunk_id = f"{doc_id}:leaf:{leaf_idx}"
                chunks.append(leaf)
                leaf_idx += 1

            sec_idx += 1

        leaf_count = sum(1 for c in chunks if c.level == "leaf")
        sec_count = sum(1 for c in chunks if c.level == "section")
        logger.info(
            "层次切片完成: %d sections, %d leaves",
            sec_count,
            leaf_count,
        )
        return chunks

    def text_for_embedding(self, chunk: IndexChunk) -> str:
        """生成用于 embedding 的文本（可选附加标题路径前缀）"""
        if (
            chunk.level != "leaf"
            or not self.prefix_heading_in_leaf
            or not chunk.heading_path
        ):
            return chunk.text
        prefix = " > ".join(chunk.heading_path)
        return f"{prefix}\n\n{chunk.text}"

    def _parse_sections(self, content: str) -> list[_Section]:
        sections: list[_Section] = []
        current_lines: list[str] = []
        current_path: list[str] = []
        heading_stack: list[tuple[int, str]] = []

        def flush():
            nonlocal current_lines, current_path
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append(
                        _Section(
                            heading_path=list(current_path),
                            lines=list(current_lines),
                        )
                    )
            current_lines = []

        for line in content.split("\n"):
            m = _HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                path = [t for _, t in heading_stack]

                if level in self.section_heading_levels:
                    flush()
                    current_path = path
                    current_lines = [line]
                else:
                    if not current_lines and not sections:
                        current_path = path
                    current_lines.append(line)
            else:
                if not current_lines and not sections and not heading_stack:
                    current_path = []
                current_lines.append(line)

        flush()
        return sections

    def _section_to_leaves(
        self,
        section: _Section,
        doc_id: str,
        section_id: str,
        lang: str,
    ) -> list[IndexChunk]:
        body_lines = list(section.lines)
        if body_lines and _HEADING_RE.match(body_lines[0]):
            body_lines = body_lines[1:]

        body = "\n".join(body_lines).strip()
        if not body:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
        raw_leaves: list[str] = []

        for para in paragraphs:
            if self._is_noise(para):
                continue
            if len(para) <= self.leaf_target_size:
                raw_leaves.append(para)
            else:
                raw_leaves.extend(
                    self._split_by_sentences(
                        para, self.leaf_target_size, self.leaf_overlap
                    )
                )

        merged = self._merge_small_leaves(raw_leaves)
        return [
            IndexChunk(
                chunk_id="",
                doc_id=doc_id,
                parent_id=section_id,
                level="leaf",
                index=0,
                text=text,
                heading_path=list(section.heading_path),
                lang=lang,
            )
            for text in merged
        ]

    def _split_by_sentences(
        self, text: str, target_size: int, overlap: int
    ) -> list[str]:
        parts = _SENTENCE_END.split(text)
        sentences = [p.strip() for p in parts if p.strip()]
        if not sentences:
            return [text] if text.strip() else []

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if current_len + sent_len + 1 > target_size and current:
                chunks.append(" ".join(current))
                overlap_text = " ".join(current)
                if overlap > 0 and len(overlap_text) > overlap:
                    overlap_text = overlap_text[-overlap:]
                    current = [overlap_text, sent]
                    current_len = len(overlap_text) + 1 + sent_len
                else:
                    current = [sent]
                    current_len = sent_len
            else:
                current.append(sent)
                current_len += sent_len + (1 if current_len else 0)

        if current:
            chunks.append(" ".join(current))

        return chunks if chunks else [text]

    def _merge_small_leaves(self, leaves: list[str]) -> list[str]:
        if not leaves:
            return []

        merged: list[str] = []
        for leaf in leaves:
            if (
                merged
                and len(leaf) < self.min_leaf_size
                and len(merged[-1]) + len(leaf) + 2 <= self.leaf_target_size * 2
            ):
                merged[-1] = merged[-1] + "\n\n" + leaf
            elif (
                merged
                and len(merged[-1]) < self.min_leaf_size
                and len(merged[-1]) + len(leaf) + 2 <= self.leaf_target_size * 2
            ):
                merged[-1] = merged[-1] + "\n\n" + leaf
            else:
                merged.append(leaf)

        return [m for m in merged if len(m.strip()) >= 1]

    @staticmethod
    def _is_noise(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if _IMAGE_ONLY_RE.match(stripped):
            return True
        if stripped.startswith("<details>") or stripped == "---":
            return True
        return False
