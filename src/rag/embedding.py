"""Embedding 客户端 - 支持 OpenAI 兼容 API 与本地 BGE-M3"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import openai

from src.infra.config import get_embedding_api_key, load_config
from src.infra.logging import get_logger

logger = get_logger("rag.embedding")


class EmbeddingClient:
    """批量文本向量化（provider: openai | bge_m3）"""

    def __init__(self, config_path: Optional[Path] = None):
        config = load_config(config_path)
        index_cfg = config.get("index", {})
        emb_cfg = index_cfg.get("embedding", {})
        self.provider = emb_cfg.get("provider", "bge_m3").lower()
        self.model = emb_cfg.get("model", "BAAI/bge-m3")
        self.batch_size = emb_cfg.get("batch_size", 12)
        self.max_concurrency = emb_cfg.get("max_concurrency", 1)
        self.model_name = self.model
        self._bge_model = None

        if self.provider == "openai":
            self._init_openai(emb_cfg)
        elif self.provider == "bge_m3":
            self._init_bge_m3(emb_cfg)
        else:
            raise ValueError(
                f"不支持的 embedding provider: {self.provider}。"
                "可选: openai, bge_m3"
            )

    def _init_openai(self, emb_cfg: dict) -> None:
        base_url = emb_cfg.get("base_url", "https://api.openai.com/v1")
        api_key = get_embedding_api_key(emb_cfg)
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = emb_cfg.get("model", "text-embedding-3-small")
        self.model_name = self.model

    def _init_bge_m3(self, emb_cfg: dict) -> None:
        self.use_fp16 = emb_cfg.get("use_fp16", True)
        self.device = emb_cfg.get("device")
        self.model = emb_cfg.get("model", "BAAI/bge-m3")
        self.model_name = self.model
        logger.info(
            "使用本地 BGE-M3: %s (fp16=%s)",
            self.model,
            self.use_fp16,
        )

    def _get_bge_model(self):
        if self._bge_model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as e:
                raise ImportError(
                    "本地 BGE-M3 需要安装 FlagEmbedding：pip install FlagEmbedding"
                ) from e

            kwargs = {"use_fp16": self.use_fp16}
            if self.device:
                kwargs["device"] = self.device
            logger.info("正在加载 BGE-M3 模型（首次较慢）...")
            self._bge_model = BGEM3FlagModel(self.model, **kwargs)
        return self._bge_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """对文本列表生成 embedding，顺序与输入一致"""
        if not texts:
            return []

        if self.provider == "bge_m3":
            return self._embed_bge_m3(texts)
        return self._embed_openai(texts)

    def _embed_bge_m3(self, texts: list[str]) -> list[list[float]]:
        model = self._get_bge_model()
        all_vectors: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            output = model.encode(
                batch,
                batch_size=len(batch),
                max_length=8192,
            )
            dense = output["dense_vecs"]
            for vec in dense:
                if hasattr(vec, "tolist"):
                    all_vectors.append(vec.tolist())
                else:
                    all_vectors.append(list(vec))

        logger.info("已向量化 %d 段文本 (BGE-M3)", len(all_vectors))
        return all_vectors

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        batches = [
            texts[i : i + self.batch_size]
            for i in range(0, len(texts), self.batch_size)
        ]
        results: list[Optional[list[list[float]]]] = [None] * len(batches)

        def embed_batch(
            batch_idx: int, batch: list[str]
        ) -> tuple[int, list[list[float]]]:
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            ordered = [
                item.embedding
                for item in sorted(response.data, key=lambda x: x.index)
            ]
            return batch_idx, ordered

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {
                executor.submit(embed_batch, i, batch): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_idx, vectors = future.result()
                results[batch_idx] = vectors

        flat: list[list[float]] = []
        for batch_vectors in results:
            if batch_vectors:
                flat.extend(batch_vectors)

        logger.info("已向量化 %d 段文本 (OpenAI)", len(flat))
        return flat
