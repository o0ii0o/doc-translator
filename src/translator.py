"""翻译引擎 - 调用 LLM API 进行翻译"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import openai

from .config_loader import get_llm_api_key, load_config
from .logger import get_logger

logger = get_logger("translator")


TRANSLATION_PROMPT = """你是一位专业的中英翻译专家。请将以下英文内容翻译成中文。

要求：
1. 保持原文的 Markdown 格式不变
2. 保留所有代码块、链接、图片引用
3. 翻译准确、通顺，符合中文表达习惯
4. 专业术语保持准确

原文：
{content}

请只输出翻译后的中文内容，不要添加额外说明。
"""


class Translator:
    """LLM 翻译引擎，支持分段处理长文本"""

    PROVIDERS = {"openai", "claude", "local"}

    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        self.llm_config = self.config.get("llm", {})
        translation_cfg = self.config.get("translation", {})
        self.provider = self.llm_config.get("provider", "openai")
        self.model = self.llm_config.get("model", "deepseek-chat")
        self.batch_size = translation_cfg.get("batch_size", 4000)
        self.max_concurrency = translation_cfg.get("max_concurrency", 3)

        self._init_client()

    def _init_client(self):
        """初始化 LLM 客户端"""
        if self.provider == "openai":
            api_key = get_llm_api_key(self.llm_config)
            base_url = self.llm_config.get("base_url")
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
            logger.info(
                "LLM 客户端已初始化: model=%s, base_url=%s, max_concurrency=%d",
                self.model,
                base_url or "default",
                self.max_concurrency,
            )
        elif self.provider == "claude":
            raise NotImplementedError("Claude provider 尚未实现")
        elif self.provider == "local":
            raise NotImplementedError("Local provider 尚未实现")
        else:
            raise ValueError(f"不支持的 provider: {self.provider}")

    def translate(self, content: str) -> str:
        """翻译内容，自动分段处理长文本"""
        logger.info("开始翻译，原文 %d 字符", len(content))

        if len(content) <= self.batch_size:
            result = self._translate_single(content, section_index=1, total_sections=1)
            logger.info("单段翻译完成，%d 字符", len(result) if result else 0)
            return result

        sections = self._split_into_sections(content)
        total = len(sections)
        workers = min(self.max_concurrency, total)
        logger.info(
            "内容已分为 %d 段，并发翻译启动 (max_workers=%d)",
            total,
            workers,
        )

        start_time = time.monotonic()
        results: list[Optional[str]] = [None] * total
        completed = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._translate_section_worker, i, total, section
                ): i
                for i, section in enumerate(sections)
            }

            for future in as_completed(futures):
                index = futures[future]
                try:
                    idx, translated = future.result()
                    results[idx] = translated
                    completed += 1
                    logger.info(
                        "总进度: %d/%d 段已完成",
                        completed,
                        total,
                    )
                except Exception as e:
                    failed += 1
                    logger.error(
                        "[段 %d/%d] 翻译失败，已失败 %d 段: %s",
                        index + 1,
                        total,
                        failed,
                        e,
                    )
                    raise

        elapsed = time.monotonic() - start_time
        result = "\n\n".join(results)
        logger.info(
            "全部段落翻译完成: %d 段, 共 %d 字符, 耗时 %.1f 秒",
            total,
            len(result),
            elapsed,
        )
        return result

    def _translate_section_worker(
        self, index: int, total: int, section: str
    ) -> tuple[int, str]:
        """线程池工作函数，返回 (index, 翻译结果) 以保持顺序"""
        section_no = index + 1
        logger.info(
            "[段 %d/%d] 开始翻译 (%d 字符)",
            section_no,
            total,
            len(section),
        )
        t0 = time.monotonic()
        translated = self._translate_single(
            section, section_index=section_no, total_sections=total
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "[段 %d/%d] 完成 (%d 字符, 耗时 %.1f 秒)",
            section_no,
            total,
            len(translated) if translated else 0,
            elapsed,
        )
        return index, translated

    def _split_into_sections(self, content: str) -> list[str]:
        """按 Markdown 标题分割内容"""
        sections = []
        current_section = []

        lines = content.split("\n")
        for line in lines:
            if re.match(r"^#{1,6}\s+", line) and current_section:
                sections.append("\n".join(current_section))
                current_section = []

            current_section.append(line)

        if current_section:
            sections.append("\n".join(current_section))

        merged = []
        for section in sections:
            if len(section) <= self.batch_size:
                merged.append(section)
            else:
                sub = self._split_by_length(section)
                logger.debug("章节过长，按长度拆分为 %d 段", len(sub))
                merged.extend(sub)

        return merged

    def _split_by_length(self, text: str) -> list[str]:
        """按长度分割文本"""
        chunks = []
        current = []

        for line in text.split("\n"):
            current.append(line)
            if sum(len(c) for c in current) >= self.batch_size:
                chunks.append("\n".join(current))
                current = []

        if current:
            chunks.append("\n".join(current))

        return chunks

    def _translate_single(
        self,
        content: str,
        section_index: int = 1,
        total_sections: int = 1,
    ) -> str:
        """翻译单段内容"""
        if self.provider == "openai":
            return self._translate_openai(
                content,
                section_index=section_index,
                total_sections=total_sections,
            )
        return ""

    def _translate_openai(
        self,
        content: str,
        section_index: int = 1,
        total_sections: int = 1,
    ) -> str:
        """使用 OpenAI API 翻译"""
        prompt = TRANSLATION_PROMPT.format(content=content)
        logger.debug(
            "[段 %d/%d] 调用 API，prompt 长度 %d",
            section_index,
            total_sections,
            len(prompt),
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的中英翻译专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
        except Exception as e:
            logger.error(
                "[段 %d/%d] API 调用失败: %s",
                section_index,
                total_sections,
                e,
            )
            raise

        result = response.choices[0].message.content
        logger.debug(
            "[段 %d/%d] API 返回 %d 字符",
            section_index,
            total_sections,
            len(result) if result else 0,
        )
        return result
