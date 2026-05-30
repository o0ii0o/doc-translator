"""Chroma 向量存储 - 仅存 leaf chunk 向量"""

from pathlib import Path
from typing import Any

import chromadb

from src.infra.logging import get_logger

logger = get_logger("storage.vector")


class VectorStore:
    """本地持久化向量库"""

    def __init__(self, vector_dir: Path | str, collection_name: str = "doc_translator"):
        self.vector_dir = Path(vector_dir)
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self._client = chromadb.PersistentClient(path=str(self.vector_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not chunk_ids:
            return
        self._collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("向量库 upsert %d 条", len(chunk_ids))

    def delete_by_doc(self, doc_id: str) -> None:
        try:
            self._collection.delete(where={"doc_id": doc_id})
            logger.info("已删除 doc_id=%s 的向量", doc_id)
        except Exception as e:
            logger.warning("删除向量失败 doc_id=%s: %s", doc_id, e)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        doc_id: str | None = None,
    ) -> list[dict]:
        """
        向量相似度检索

        Returns:
            list[dict]: chunk_id, distance, metadata
        """
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["metadatas", "distances"],
        }
        if doc_id:
            kwargs["where"] = {"doc_id": doc_id}

        result = self._collection.query(**kwargs)
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        hits = []
        for i, chunk_id in enumerate(ids):
            dist = distances[i] if i < len(distances) else 0.0
            meta = metadatas[i] if i < len(metadatas) else {}
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "distance": dist,
                    "metadata": meta or {},
                }
            )
        logger.info("向量检索返回 %d 条 (doc_id=%s)", len(hits), doc_id or "*")
        return hits
