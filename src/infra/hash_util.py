"""文件哈希工具"""

import hashlib
from pathlib import Path


def compute_file_hash(file_path: Path) -> str:
    """计算文件 SHA256（分块读取，适用于大文件）"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
