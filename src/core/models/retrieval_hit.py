"""检索命中结果"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RetrievalHit:
    """向量检索命中的一条 leaf"""

    chunk_id: str
    doc_id: str
    parent_id: Optional[str]
    score: float
    distance: float
    leaf_text: str
    heading_path: list[str] = field(default_factory=list)
    parent_text: Optional[str] = None
    section_heading: str = ""
