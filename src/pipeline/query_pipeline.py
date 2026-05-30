"""RAG 问答流水线 - 单文档检索 + 中文回答"""

from pathlib import Path
from typing import Optional

from src.infra.config import load_config
from src.infra.logging import get_logger
from src.rag.answer import AnswerGenerator
from src.rag.context_builder import build_context
from src.rag.retrieval import Retriever
from src.storage.document_store import DocumentStore

logger = get_logger("pipeline")


def run_query_pipeline(
    question: str,
    doc_id: str,
    config_path: Path,
) -> dict:
    """
    在单篇文档内检索并生成中文答案

    Returns:
        answer, sources, doc_id, doc_title, hit_count
    """
    if not question.strip():
        raise ValueError("问题不能为空")
    if not doc_id.strip():
        raise ValueError("必须指定 doc_id（单文档查询）")

    config = load_config(config_path)
    query_cfg = config.get("query", {})
    index_cfg = config.get("index", {})
    db_path = Path(index_cfg.get("db_path", "data/doc_translator.db"))

    store = DocumentStore(db_path)
    doc = store.get_document(doc_id)
    if not doc:
        raise ValueError(f"文档不存在: {doc_id}")

    retriever = Retriever(config_path)
    hits = retriever.retrieve(question, doc_id)

    context, sources = build_context(
        hits,
        max_context_chars=query_cfg.get("max_context_chars", 8000),
        use_parent_context=query_cfg.get("use_parent_context", True),
    )

    generator = AnswerGenerator(config_path)
    answer = generator.generate(question, context, doc.title)

    return {
        "answer": answer,
        "sources": sources,
        "doc_id": doc_id,
        "doc_title": doc.title,
        "hit_count": len(hits),
    }


def format_query_output(result: dict, *, include_sources: bool = True) -> str:
    """格式化终端输出"""
    lines = [
        f"文档: {result['doc_title']} ({result['doc_id']})",
        f"检索命中: {result['hit_count']} 条",
        "",
        "## 回答",
        "",
        result["answer"],
    ]

    if include_sources and result.get("sources"):
        lines.extend(["", "## 参考来源", ""])
        for s in result["sources"]:
            lines.append(
                f"- [{s['score']}] {s['heading']} ({s['chunk_id']}, {s['type']})"
            )

    return "\n".join(lines)
