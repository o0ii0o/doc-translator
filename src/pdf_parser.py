"""PDF 解析器 - 使用 MinerU API 提取 PDF 内容"""

from pathlib import Path
from typing import Optional

from .config_loader import get_mineru_token, load_config
from .logger import get_logger
from .minerU_api_parse import parse_local_pdf
from .parse_cache import ParseCache

logger = get_logger("pdf_parser")


class PDFParser:
    """使用 MinerU 云端 API 解析 PDF 文件，支持解析结果缓存"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        mineru_config = self.config.get("mineru", {})
        cache_config = self.config.get("cache", {})

        self.mineru_model = mineru_config.get("model", "vlm")
        self.api_base = mineru_config.get(
            "base_url", "https://mineru.net/api/v4"
        )
        self.token = get_mineru_token(mineru_config)
        self.poll_interval = mineru_config.get("poll_interval", 5)
        self.max_poll_attempts = mineru_config.get("max_poll_attempts", 600)
        connect_timeout = mineru_config.get("connect_timeout", 10)
        read_timeout = mineru_config.get("read_timeout", 120)
        self.timeout = (connect_timeout, read_timeout)

        self.cache = ParseCache(
            cache_dir=cache_config.get("dir", ".cache/parse"),
            enabled=cache_config.get("enabled", True),
        )
        self.use_cache = cache_config.get("enabled", True)

        logger.debug(
            "MinerU 配置: model=%s, base_url=%s, cache=%s",
            self.mineru_model,
            self.api_base,
            self.use_cache,
        )

    def parse(self, pdf_path: Path, *, force: bool = False) -> str:
        """解析 PDF 文件并返回 Markdown 内容"""
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        file_hash = None
        if self.use_cache:
            file_hash = self.cache.compute_hash(pdf_path)

        if self.use_cache and not force:
            cached = self.cache.get(pdf_path, self.mineru_model, file_hash=file_hash)
            if cached is not None:
                return cached

        logger.info("开始解析 PDF (MinerU API): %s", pdf_path.name)
        content = parse_local_pdf(
            pdf_path,
            self.api_base,
            self.token,
            self.mineru_model,
            poll_interval=self.poll_interval,
            max_poll_attempts=self.max_poll_attempts,
            timeout=self.timeout,
        )

        if self.use_cache:
            self.cache.set(
                pdf_path, self.mineru_model, content, file_hash=file_hash
            )

        return content
