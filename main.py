#!/usr/bin/env python3
"""文档翻译系统入口脚本"""

import sys
import argparse
from pathlib import Path

from src.config_loader import load_config
from src.file_handler import FileHandler
from src.logger import get_logger, setup_logging, setup_logging_from_config
from src.translator import Translator
from src.output import OutputManager

logger = get_logger("main")


def main():
    parser = argparse.ArgumentParser(
        description="文档翻译系统 - PDF/Markdown 英译中"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="要翻译的文件路径 (PDF 或 Markdown)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="输出文件路径 (默认: {原文件名}_zh.md)"
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出 DEBUG 级别日志"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="日志文件路径（覆盖 config.yaml 中的设置）"
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="禁用文件日志，仅输出到控制台"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用解析缓存，强制重新调用 MinerU 解析"
    )

    args = parser.parse_args()

    config = load_config(args.config)
    if args.no_cache:
        config.setdefault("cache", {})["enabled"] = False
    if args.verbose:
        config.setdefault("logging", {})["level"] = "DEBUG"
    if args.no_log_file:
        config.setdefault("logging", {})["file"] = None
    elif args.log_file:
        config.setdefault("logging", {})["file"] = str(args.log_file)

    setup_logging_from_config(config)

    if not args.input_file.exists():
        logger.error("文件不存在: %s", args.input_file)
        sys.exit(1)

    try:
        logger.info("开始处理: %s", args.input_file)

        handler = FileHandler(args.config)
        content = handler.process(args.input_file, force_parse=args.no_cache)
        logger.info("内容提取完成，共 %d 字符", len(content))

        translator = Translator(args.config)
        translated = translator.translate(content)
        logger.info("翻译完成，共 %d 字符", len(translated))

        output_path = args.output or args.input_file.with_name(
            f"{args.input_file.stem}_zh.md"
        )

        output = OutputManager()
        output.write(output_path, translated)

        logger.info("结果已保存: %s", output_path)

    except ValueError as e:
        logger.error("配置错误: %s", e)
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        err = str(e)
        if "401" in err or "authentication" in err.lower():
            logger.error(
                "翻译 API 认证失败（MinerU 解析可能已成功），"
                "请检查 DEEPSEEK_API_KEY 或 OPENAI_API_KEY"
            )
        logger.exception("处理失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
