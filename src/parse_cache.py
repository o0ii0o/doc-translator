"""PDF 解析结果缓存"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .logger import get_logger

logger = get_logger("cache")


class ParseCache:
    """按 PDF 文件内容哈希缓存 MinerU 解析后的 Markdown"""

    def __init__(
        self,
        cache_dir: Path | str = ".cache/parse",
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir)
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_hash(self, file_path: Path) -> str:
        """计算文件 SHA256（分块读取，适用于大文件）"""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _cache_key(self, file_hash: str, model: str) -> str:
        return f"{file_hash}_{model}"

    def _md_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.md"

    def _meta_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.meta.json"

    def compute_hash(self, pdf_path: Path) -> str:
        return self._file_hash(Path(pdf_path))

    def get(self, pdf_path: Path, model: str, file_hash: Optional[str] = None) -> Optional[str]:
        """命中缓存则返回 Markdown，否则返回 None"""
        if not self.enabled:
            return None

        pdf_path = Path(pdf_path)
        file_hash = file_hash or self._file_hash(pdf_path)
        key = self._cache_key(file_hash, model)
        md_path = self._md_path(key)
        meta_path = self._meta_path(key)

        if not md_path.exists() or not meta_path.exists():
            logger.debug("缓存未命中: %s", pdf_path.name)
            return None

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("model") != model:
            logger.info("缓存模型不匹配，将重新解析: %s", pdf_path.name)
            return None

        content = md_path.read_text(encoding="utf-8")
        logger.info(
            "命中解析缓存: %s (%d 字符, 缓存于 %s)",
            pdf_path.name,
            len(content),
            meta.get("cached_at", "未知"),
        )
        return content

    def set(
        self,
        pdf_path: Path,
        model: str,
        markdown: str,
        file_hash: Optional[str] = None,
    ) -> None:
        """写入解析缓存"""
        if not self.enabled:
            return

        pdf_path = Path(pdf_path)
        file_hash = file_hash or self._file_hash(pdf_path)
        key = self._cache_key(file_hash, model)
        md_path = self._md_path(key)
        meta_path = self._meta_path(key)

        md_path.write_text(markdown, encoding="utf-8")
        meta = {
            "source_name": pdf_path.name,
            "source_path": str(pdf_path.resolve()),
            "file_size": pdf_path.stat().st_size,
            "file_hash": file_hash,
            "model": model,
            "char_count": len(markdown),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "已写入解析缓存: %s -> %s",
            pdf_path.name,
            md_path.name,
        )
