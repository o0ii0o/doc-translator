"""知识库文档数据模型"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Document:
    """已入库文档元数据"""

    doc_id: str
    file_hash: str
    source_path: str
    title: str
    lang: str
    char_count: int
    status: str
    parsed_path: Optional[str]
    created_at: str
    updated_at: str
