"""翻译流水线编排"""

from pathlib import Path

from src.chunking.markdown_chunker import MarkdownChunker
from src.infra.logging import get_logger
from src.parser.router import DocumentRouter
from src.translator.translator import Translator

logger = get_logger("pipeline")


def run_translate_pipeline(
    file_path: Path,
    config_path: Path,
    *,
    force_parse: bool = False,
) -> str:
    """
    执行完整翻译流程：解析 → 切分 → 翻译 → 拼接

    Returns:
        翻译后的 Markdown 文本
    """
    router = DocumentRouter(config_path)
    content = router.process(file_path, force_parse=force_parse)
    logger.info("内容提取完成，共 %d 字符", len(content))

    chunker = MarkdownChunker(config_path=config_path)
    chunks = chunker.split(content)

    if not chunks:
        logger.warning("无有效文本块，返回空结果")
        return ""

    translator = Translator(config_path)
    logger.info("开始翻译，原文 %d 字符", len(content))

    if len(chunks) == 1:
        translated_parts = [translator.translate_text(chunks[0].text)]
    else:
        translated_parts = translator.translate_chunks(chunks)

    result = "\n\n".join(translated_parts)
    logger.info("翻译完成，共 %d 字符", len(result))
    return result
