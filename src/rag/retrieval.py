"""RAG 检索 - 单文档向量检索 + SQLite 回填"""

from pathlib import Path
from typing import Optional

from src.core.models.retrieval_hit import RetrievalHit
from src.infra.config import load_config
from src.infra.logging import get_logger
from src.rag.embedding import EmbeddingClient
from src.storage.document_store import DocumentStore
from src.storage.vector_store import VectorStore

logger = get_logger("rag.retrieval")


class Retriever:
    """在指定文档内做 leaf 向量检索，并加载父子上下文"""

    def __init__(self, config_path: Optional[Path] = None):
        config = load_config(config_path)
        index_cfg = config.get("index", {})
        query_cfg = config.get("query", {})

        self.db_path = Path(index_cfg.get("db_path", "data/doc_translator.db"))
        self.vector_dir = Path(index_cfg.get("vector_dir", "data/vector"))
        self.collection = index_cfg.get("collection_name", "doc_translator")
        self.top_k = query_cfg.get("top_k", 6)
        self.max_distance = query_cfg.get("max_distance")
        self.use_parent_context = query_cfg.get("use_parent_context", True)

        self.store = DocumentStore(self.db_path)
        self.vector_store = VectorStore(self.vector_dir, self.collection)
        self.embedder = EmbeddingClient(config_path)

    def retrieve(self, question: str, doc_id: str) -> list[RetrievalHit]:
        doc = self.store.get_document(doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")
        if doc.status != "indexed":
            raise ValueError(
                f"文档尚未向量化 (status={doc.status})，请先执行: "
                f"python main.py index --doc-id {doc_id}"
            )

        query_vec = self.embedder.embed_texts([question])[0]
        raw_hits = self.vector_store.query(
            query_vec, top_k=self.top_k, doc_id=doc_id
        )

        hits: list[RetrievalHit] = []
        for item in raw_hits:
            dist = item["distance"]
            if self.max_distance is not None and dist > self.max_distance:
                continue

            chunk_id = item["chunk_id"]
            leaf = self.store.get_chunk_by_id(chunk_id)
            if not leaf:
                logger.warning("chunk 不存在: %s", chunk_id)
                continue

            parent_text = None
            section_heading = ""
            if self.use_parent_context and leaf.parent_id:
                parent = self.store.get_chunk_by_id(leaf.parent_id)
                if parent:
                    parent_text = parent.text
                    section_heading = (
                        " > ".join(parent.heading_path)
                        if parent.heading_path
                        else ""
                    )

            similarity = 1.0 - dist if dist <= 1.0 else 1.0 / (1.0 + dist)
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    parent_id=leaf.parent_id,
                    score=similarity,
                    distance=dist,
                    leaf_text=leaf.text,
                    heading_path=list(leaf.heading_path),
                    parent_text=parent_text,
                    section_heading=section_heading,
                )
            )

        logger.info("检索完成 doc_id=%s 命中 %d 条", doc_id, len(hits))
        return hits
