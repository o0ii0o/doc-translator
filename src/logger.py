"""日志配置模块"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "doc_translator"
_configured = False

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """初始化全局日志配置，重复调用无效"""
    global _configured
    if _configured:
        return

    log_level = _LEVEL_MAP.get(level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(log_level)
    root.propagate = False

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _configured = True
    root.debug("日志系统已初始化，级别=%s", level.upper())


def setup_logging_from_config(config: dict) -> None:
    """从 config.yaml 的 logging 段加载配置"""
    log_cfg = config.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file"),
        console=log_cfg.get("console", True),
        max_bytes=log_cfg.get("max_bytes", 5 * 1024 * 1024),
        backup_count=log_cfg.get("backup_count", 3),
    )


def get_logger(module: str) -> logging.Logger:
    """获取模块级 logger，使用前需先调用 setup_logging"""
    return logging.getLogger(f"{_LOGGER_NAME}.{module}")
