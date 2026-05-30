"""知识库向量化流水线"""

from pathlib import Path
from typing import Optional

from src.chunking.hierarchical_chunker import HierarchicalChunker
from src.infra.config import load_config
from src.infra.logging import get_logger
from src.rag.embedding import EmbeddingClient
from src.storage.document_store import DocumentStore
from src.storage.vector_store import VectorStore

logger = get_logger("pipeline")


def run_index_pipeline(
    config_path: Path,
    *,
    doc_id: Optional[str] = None,
    all_docs: bool = False,
    force: bool = False,
) -> list[dict]:
    """
    对未向量化的 leaf chunks 做 embedding 并写入 Chroma

    Returns:
        每个文档的处理结果列表
    """
    config = load_config(config_path)
    index_cfg = config.get("index", {})
    db_path = Path(index_cfg.get("db_path", "data/doc_translator.db"))
    vector_dir = Path(index_cfg.get("vector_dir", "data/vector"))
    collection = index_cfg.get("collection_name", "doc_translator")

    store = DocumentStore(db_path)
    vector_store = VectorStore(vector_dir, collection)
    embedder = EmbeddingClient(config_path)
    chunker = HierarchicalChunker(config_path)

    if doc_id:
        doc_ids = [doc_id]
    elif all_docs:
        if force:
            doc_ids = [d.doc_id for d in store.list_documents()]
        else:
            doc_ids = store.list_doc_ids_by_status("chunked")
    else:
        raise ValueError("请指定 --doc-id 或 --all")

    results = []
    for did in doc_ids:
        doc = store.get_document(did)
        if not doc:
            logger.warning("文档不存在: %s", did)
            continue

        if force:
            vector_store.delete_by_doc(did)
            store.reset_embedded(did)

        leaves = store.get_unembedded_leaves(did)
        if not leaves:
            logger.info("无待向量化 leaf (doc_id=%s)", did)
            if doc.status != "indexed":
                store.update_status(did, "indexed")
            results.append(
                {"doc_id": did, "embedded_count": 0, "skipped": True}
            )
            continue

        texts = [chunker.text_for_embedding(leaf) for leaf in leaves]
        embeddings = embedder.embed_texts(texts)

        if len(embeddings) != len(leaves):
            raise RuntimeError(
                f"embedding 数量不匹配: {len(embeddings)} vs {len(leaves)}"
            )

        metadatas = [
            {
                "doc_id": leaf.doc_id,
                "parent_id": leaf.parent_id or "",
                "level": leaf.level,
                "index": leaf.index,
            }
            for leaf in leaves
        ]
        chunk_ids = [leaf.chunk_id for leaf in leaves]

        vector_store.upsert(chunk_ids, embeddings, metadatas)
        store.mark_embedded(chunk_ids, embedder.model_name)
        store.update_status(did, "indexed")

        logger.info(
            "向量化完成 doc_id=%s embedded=%d",
            did,
            len(leaves),
        )
        results.append(
            {"doc_id": did, "embedded_count": len(leaves), "skipped": False}
        )

    return results
