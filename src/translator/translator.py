"""翻译引擎 - 调用 LLM API 进行翻译"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import openai

from src.core.models.chunk import Chunk
from src.infra.config import get_llm_api_key, load_config
from src.infra.logging import get_logger

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
    """LLM 翻译引擎，仅负责调用 API 翻译文本块"""

    PROVIDERS = {"openai", "claude", "local"}

    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        self.llm_config = self.config.get("llm", {})
        translation_cfg = self.config.get("translation", {})
        self.provider = self.llm_config.get("provider", "openai")
        self.model = self.llm_config.get("model", "deepseek-chat")
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

    def translate_text(self, text: str) -> str:
        """翻译单块文本"""
        return self._translate_openai(text, section_index=1, total_sections=1)

    def translate_chunks(self, chunks: list[Chunk]) -> list[str]:
        """并发翻译多个文本块，按 index 保序返回"""
        if not chunks:
            return []

        total = len(chunks)

        if total == 1:
            result = self.translate_text(chunks[0].text)
            logger.info("单段翻译完成，%d 字符", len(result) if result else 0)
            return [result]

        workers = min(self.max_concurrency, total)
        logger.info("并发翻译启动 (max_workers=%d, 共 %d 段)", workers, total)

        start_time = time.monotonic()
        results: list[Optional[str]] = [None] * total
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._translate_chunk_worker, chunk, total
                ): chunk.index
                for chunk in chunks
            }

            for future in as_completed(futures):
                index = futures[future]
                try:
                    idx, translated = future.result()
                    results[idx] = translated
                    completed += 1
                    logger.info("总进度: %d/%d 段已完成", completed, total)
                except Exception as e:
                    logger.error(
                        "[段 %d/%d] 翻译失败: %s",
                        index + 1,
                        total,
                        e,
                    )
                    raise

        elapsed = time.monotonic() - start_time
        logger.info("全部段落翻译完成: %d 段, 耗时 %.1f 秒", total, elapsed)
        return results

    def _translate_chunk_worker(
        self, chunk: Chunk, total: int
    ) -> tuple[int, str]:
        """线程池工作函数"""
        section_no = chunk.index + 1
        logger.info(
            "[段 %d/%d] 开始翻译 (%d 字符)",
            section_no,
            total,
            chunk.char_count,
        )
        t0 = time.monotonic()
        translated = self._translate_openai(
            chunk.text,
            section_index=section_no,
            total_sections=total,
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "[段 %d/%d] 完成 (%d 字符, 耗时 %.1f 秒)",
            section_no,
            total,
            len(translated) if translated else 0,
            elapsed,
        )
        return chunk.index, translated

    def _translate_openai(
        self,
        content: str,
        section_index: int = 1,
        total_sections: int = 1,
    ) -> str:
        """使用 OpenAI 兼容 API 翻译"""
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
