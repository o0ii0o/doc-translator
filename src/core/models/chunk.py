"""文本块数据模型"""

from dataclasses import dataclass


@dataclass
class Chunk:
    """可复用于翻译、向量化、索引的文本块"""

    index: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)
