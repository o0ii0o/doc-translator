"""知识库索引块数据模型"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IndexChunk:
    """层次切片节点（section 或 leaf）"""

    chunk_id: str
    doc_id: str
    parent_id: Optional[str]
    level: str
    index: int
    text: str
    heading_path: list[str] = field(default_factory=list)
    lang: str = ""
    char_count: int = 0
    embedded: bool = False

    def __post_init__(self):
        if not self.char_count:
            self.char_count = len(self.text)
