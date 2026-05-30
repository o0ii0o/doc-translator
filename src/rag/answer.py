"""基于检索上下文生成中文回答"""

from pathlib import Path
from typing import Optional

import openai

from src.infra.config import get_llm_api_key, load_config
from src.infra.logging import get_logger

logger = get_logger("rag.answer")

RAG_PROMPT = """你是一位学术论文阅读助手。请根据下面从文档《{title}》中检索到的节选内容，用中文回答用户问题。

要求：
1. 仅依据提供的上下文作答，不要编造文档中未出现的信息
2. 若上下文不足以回答，请明确说明「根据当前检索内容无法确定」
3. 回答使用简体中文，表述准确、条理清晰
4. 如涉及方法、结论、数据，尽量对应到具体章节

检索上下文：
{context}

用户问题：
{question}
"""


class AnswerGenerator:
    """调用 LLM 生成 RAG 回答（默认中文）"""

    def __init__(self, config_path: Optional[Path] = None):
        config = load_config(config_path)
        self.llm_config = config.get("llm", {})
        query_cfg = config.get("query", {})
        self.model = self.llm_config.get("model", "deepseek-chat")
        self.temperature = query_cfg.get("temperature", 0.3)
        self.answer_lang = query_cfg.get("answer_lang", "zh")

        api_key = get_llm_api_key(self.llm_config)
        base_url = self.llm_config.get("base_url")
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self, question: str, context: str, doc_title: str
    ) -> str:
        if not context.strip():
            return "未检索到相关内容，无法回答。请尝试换一种问法或确认文档已完成向量化。"

        prompt = RAG_PROMPT.format(
            title=doc_title,
            context=context,
            question=question,
        )
        system = (
            "你是一位学术论文阅读助手，擅长根据给定节选用中文准确回答问题。"
        )

        logger.info("调用 LLM 生成回答 (model=%s)", self.model)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
        )
        answer = response.choices[0].message.content or ""
        logger.info("回答生成完成，%d 字符", len(answer))
        return answer.strip()
