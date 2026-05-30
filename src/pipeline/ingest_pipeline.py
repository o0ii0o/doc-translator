"""知识库入库流水线"""

from pathlib import Path

import langdetect

from src.chunking.hierarchical_chunker import HierarchicalChunker
from src.core.models.document import Document
from src.infra.config import load_config
from src.infra.hash_util import compute_file_hash
from src.infra.logging import get_logger
from src.parser.router import DocumentRouter
from src.storage.document_store import DocumentStore, _utc_now

logger = get_logger("pipeline")


def _detect_lang(text: str) -> str:
    sample = text[:5000].strip()
    if not sample:
        return "unknown"
    try:
        return langdetect.detect(sample)
    except langdetect.LangDetectException:
        return "unknown"


def _make_doc_id(file_hash: str) -> str:
    return file_hash[:16]


def run_ingest_pipeline(
    file_path: Path,
    config_path: Path,
    *,
    force: bool = False,
    force_parse: bool = False,
) -> dict:
    """
    解析 → 层次切片 → SQLite 入库

    Returns:
        dict: doc_id, skipped, section_count, leaf_count, file_hash
    """
    file_path = Path(file_path).resolve()
    config = load_config(config_path)
    index_cfg = config.get("index", {})

    db_path = Path(index_cfg.get("db_path", "data/doc_translator.db"))
    parsed_dir = Path(index_cfg.get("parsed_dir", "data/parsed"))
    parsed_dir.mkdir(parents=True, exist_ok=True)

    store = DocumentStore(db_path)
    file_hash = compute_file_hash(file_path)

    existing = store.get_by_file_hash(file_hash)
    if existing and not force:
        chunks = store.get_chunks_by_doc(existing.doc_id)
        leaf_count = sum(1 for c in chunks if c.level == "leaf")
        sec_count = sum(1 for c in chunks if c.level == "section")
        logger.info(
            "文档已入库，跳过 (doc_id=%s, file_hash=%s)",
            existing.doc_id,
            file_hash[:12],
        )
        return {
            "doc_id": existing.doc_id,
            "skipped": True,
            "section_count": sec_count,
            "leaf_count": leaf_count,
            "file_hash": file_hash,
        }

    router = DocumentRouter(config_path)
    content = router.process(file_path, force_parse=force_parse)
    logger.info("内容提取完成，共 %d 字符", len(content))

    lang = _detect_lang(content)
    doc_id = existing.doc_id if existing else _make_doc_id(file_hash)
    title = file_path.stem

    chunker = HierarchicalChunker(config_path)
    chunks = chunker.split(content, doc_id=doc_id, lang=lang)

    if not chunks:
        raise ValueError("切片结果为空，无法入库")

    parsed_path = parsed_dir / f"{doc_id}.md"
    parsed_path.write_text(content, encoding="utf-8")

    now = _utc_now()

    doc = Document(
        doc_id=doc_id,
        file_hash=file_hash,
        source_path=str(file_path),
        title=title,
        lang=lang,
        char_count=len(content),
        status="chunked",
        parsed_path=str(parsed_path),
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )

    store.upsert_document(doc)
    store.replace_chunks(doc_id, chunks)

    if existing and force:
        try:
            from src.storage.vector_store import VectorStore

            vector_dir = Path(index_cfg.get("vector_dir", "data/vector"))
            collection = index_cfg.get("collection_name", "doc_translator")
            VectorStore(vector_dir, collection).delete_by_doc(doc_id)
            store.reset_embedded(doc_id)
            store.update_status(doc_id, "chunked")
        except Exception as e:
            logger.warning("清理旧向量失败（可忽略）: %s", e)

    sec_count = sum(1 for c in chunks if c.level == "section")
    leaf_count = sum(1 for c in chunks if c.level == "leaf")
    logger.info(
        "入库完成 doc_id=%s sections=%d leaves=%d lang=%s",
        doc_id,
        sec_count,
        leaf_count,
        lang,
    )

    return {
        "doc_id": doc_id,
        "skipped": False,
        "section_count": sec_count,
        "leaf_count": leaf_count,
        "file_hash": file_hash,
    }
