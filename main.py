#!/usr/bin/env python3
"""文档翻译与知识库入库入口"""

import sys
import argparse
from pathlib import Path

from src.infra.config import load_config
from src.infra.logging import get_logger, setup_logging_from_config
from src.io.output import OutputManager
from src.pipeline.ingest_pipeline import run_ingest_pipeline
from src.pipeline.index_pipeline import run_index_pipeline
from src.pipeline.query_pipeline import format_query_output, run_query_pipeline
from src.pipeline.translate_pipeline import run_translate_pipeline

logger = get_logger("main")

_SUBCOMMANDS = ("translate", "ingest", "index", "query")


def _apply_logging_args(config: dict, args) -> None:
    if getattr(args, "no_cache", False):
        config.setdefault("cache", {})["enabled"] = False
    if getattr(args, "verbose", False):
        config.setdefault("logging", {})["level"] = "DEBUG"
    if getattr(args, "no_log_file", False):
        config.setdefault("logging", {})["file"] = None
    elif getattr(args, "log_file", None):
        config.setdefault("logging", {})["file"] = str(args.log_file)
    setup_logging_from_config(config)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="配置文件路径 (默认: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出 DEBUG 级别日志",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="日志文件路径（覆盖 config.yaml）",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="禁用文件日志",
    )


def cmd_translate(args) -> None:
    if not args.input_file.exists():
        logger.error("文件不存在: %s", args.input_file)
        sys.exit(1)

    config = load_config(args.config)
    _apply_logging_args(config, args)

    logger.info("开始翻译: %s", args.input_file)
    translated = run_translate_pipeline(
        args.input_file,
        args.config,
        force_parse=args.no_cache,
    )
    output_path = args.output or args.input_file.with_name(
        f"{args.input_file.stem}_zh.md"
    )
    OutputManager().write(output_path, translated)
    logger.info("结果已保存: %s", output_path)


def cmd_ingest(args) -> None:
    if not args.input_file.exists():
        logger.error("文件不存在: %s", args.input_file)
        sys.exit(1)

    config = load_config(args.config)
    _apply_logging_args(config, args)

    logger.info("开始入库: %s", args.input_file)
    result = run_ingest_pipeline(
        args.input_file,
        args.config,
        force=args.force,
        force_parse=args.no_cache,
    )
    logger.info(
        "入库结果 doc_id=%s skipped=%s sections=%d leaves=%d",
        result["doc_id"],
        result["skipped"],
        result["section_count"],
        result["leaf_count"],
    )

    if args.index and not result["skipped"]:
        logger.info("继续向量化 doc_id=%s", result["doc_id"])
        index_results = run_index_pipeline(
            args.config,
            doc_id=result["doc_id"],
            force=args.force,
        )
        for ir in index_results:
            logger.info(
                "向量化 doc_id=%s count=%d",
                ir["doc_id"],
                ir["embedded_count"],
            )


def cmd_query(args) -> None:
    if not args.doc_id:
        logger.error("单文档查询必须指定 --doc-id")
        sys.exit(1)

    config = load_config(args.config)
    _apply_logging_args(config, args)

    logger.info("问答 doc_id=%s", args.doc_id)
    result = run_query_pipeline(
        args.question,
        args.doc_id,
        args.config,
    )
    output = format_query_output(
        result,
        include_sources=not args.no_sources,
    )
    print(output)


def cmd_index(args) -> None:
    config = load_config(args.config)
    _apply_logging_args(config, args)

    if not args.doc_id and not args.all_docs:
        logger.error("请指定 --doc-id 或 --all")
        sys.exit(1)

    results = run_index_pipeline(
        args.config,
        doc_id=args.doc_id,
        all_docs=args.all_docs,
        force=args.force,
    )
    if not results:
        logger.warning("没有可处理的文档")
        return
    for r in results:
        logger.info(
            "doc_id=%s embedded=%d skipped=%s",
            r["doc_id"],
            r["embedded_count"],
            r["skipped"],
        )


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in _SUBCOMMANDS and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "translate")

    parser = argparse.ArgumentParser(
        description="文档翻译与 RAG 知识库工具"
    )
    _add_common_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_translate = subparsers.add_parser("translate", help="翻译 PDF/Markdown 为中文")
    p_translate.add_argument("input_file", type=Path, help="输入文件路径")
    p_translate.add_argument(
        "-o", "--output", type=Path, help="输出路径 (默认: {原名}_zh.md)"
    )
    p_translate.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用解析缓存",
    )
    p_translate.set_defaults(func=cmd_translate)

    p_ingest = subparsers.add_parser("ingest", help="解析并入库到知识库")
    p_ingest.add_argument("input_file", type=Path, help="输入文件路径")
    p_ingest.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用解析缓存，强制重新解析",
    )
    p_ingest.add_argument(
        "--force",
        action="store_true",
        help="强制重新切片入库（同文件哈希）",
    )
    p_ingest.add_argument(
        "--index",
        action="store_true",
        help="入库后立即向量化",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_index = subparsers.add_parser("index", help="对已入库文档做 embedding")
    p_index.add_argument("--doc-id", type=str, help="指定文档 ID")
    p_index.add_argument(
        "--all",
        dest="all_docs",
        action="store_true",
        help="处理所有 status=chunked 的文档",
    )
    p_index.add_argument(
        "--force",
        action="store_true",
        help="强制重新向量化",
    )
    p_index.set_defaults(func=cmd_index)

    p_query = subparsers.add_parser(
        "query", help="在单篇已索引文档内问答（默认中文）"
    )
    p_query.add_argument("question", type=str, help="用户问题")
    p_query.add_argument(
        "--doc-id",
        type=str,
        required=True,
        help="文档 ID（ingest 时输出的 doc_id）",
    )
    p_query.add_argument(
        "--no-sources",
        action="store_true",
        help="不输出参考来源列表",
    )
    p_query.set_defaults(func=cmd_query)

    args = parser.parse_args()

    try:
        args.func(args)
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
                "API 认证失败，请检查 DEEPSEEK_API_KEY / OPENAI_API_KEY / MINERU_API_KEY"
            )
        logger.exception("处理失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
