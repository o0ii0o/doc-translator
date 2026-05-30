"""将检索结果拼装为 LLM 上下文"""

from src.core.models.retrieval_hit import RetrievalHit
from src.infra.logging import get_logger

logger = get_logger("rag.context")


def build_context(
    hits: list[RetrievalHit],
    *,
    max_context_chars: int = 8000,
    use_parent_context: bool = True,
) -> tuple[str, list[dict]]:
    """
    拼装上下文并生成来源列表

    Returns:
        (context_text, sources)
    """
    if not hits:
        return "", []

    parts: list[str] = []
    sources: list[dict] = []
    used_parents: set[str] = set()
    total_chars = 0

    for i, hit in enumerate(hits, 1):
        heading = " > ".join(hit.heading_path) if hit.heading_path else f"片段 {i}"
        source_label = f"【来源 {i}】{heading}"

        if use_parent_context and hit.parent_id and hit.parent_id not in used_parents:
            block_text = hit.parent_text or hit.leaf_text
            used_parents.add(hit.parent_id)
            block_type = "section"
        else:
            block_text = hit.leaf_text
            block_type = "leaf"

        block = f"{source_label}\n{block_text}"
        if total_chars + len(block) > max_context_chars:
            remaining = max_context_chars - total_chars
            if remaining <= 200:
                logger.warning("上下文已达上限，截断后续来源")
                break
            block = block[:remaining] + "\n...(已截断)"
            parts.append(block)
            total_chars = max_context_chars
            sources.append(
                {
                    "chunk_id": hit.chunk_id,
                    "heading": heading,
                    "score": round(hit.score, 4),
                    "type": block_type,
                    "truncated": True,
                }
            )
            break

        parts.append(block)
        total_chars += len(block)
        sources.append(
            {
                "chunk_id": hit.chunk_id,
                "heading": heading,
                "score": round(hit.score, 4),
                "type": block_type,
                "truncated": False,
            }
        )

    context = "\n\n---\n\n".join(parts)
    logger.info("上下文长度 %d 字符，来源 %d 条", len(context), len(sources))
    return context, sources
