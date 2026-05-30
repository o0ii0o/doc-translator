"""输出模块 - 生成翻译后的 Markdown 文件"""

from pathlib import Path

from src.infra.logging import get_logger

logger = get_logger("output")


class OutputManager:
    """管理翻译结果输出"""

    def write(self, output_path: Path, content: str) -> None:
        """将翻译内容写入文件"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("已写入 %s (%d 字符)", output_path, len(content))
