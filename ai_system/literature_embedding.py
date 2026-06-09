"""
文献检索用的 embedding 工具。

通过 OpenAI 兼容接口（走 .env 里配置的 base_url，如 yunwu）计算文本向量，
用于内部文献库的语义检索。失败时上层会回退到分词检索，所以这里只需在
出错时返回 None，不抛异常。
"""

import logging
import math
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_EMBED_MODEL = os.environ.get("LITERATURE_EMBED_MODEL", "text-embedding-3-small")

# 进程内缓存：文本 -> 向量，避免重复计算同一段文本
_embed_cache = {}


def embedding_enabled() -> bool:
    """是否启用 embedding 检索。设 LITERATURE_EMBED=0 可关闭（强制走分词）。"""
    return os.environ.get("LITERATURE_EMBED", "1") not in ("0", "false", "False", "")


def get_embedding(text: str, model: Optional[str] = None) -> Optional[List[float]]:
    """算单段文本的 embedding。失败返回 None（上层回退分词）。"""
    if not text or not text.strip():
        return None
    if not embedding_enabled():
        return None
    key = (model or _DEFAULT_EMBED_MODEL, text)
    if key in _embed_cache:
        return _embed_cache[key]
    try:
        # 延迟导入，避免无 openai 环境时整模块导入失败
        from openai import OpenAI

        client = OpenAI()  # base_url / api_key 走环境变量
        resp = client.embeddings.create(
            model=model or _DEFAULT_EMBED_MODEL,
            input=text[:8000],  # 截断，避免超长输入
        )
        vec = resp.data[0].embedding
        _embed_cache[key] = vec
        return vec
    except Exception as e:
        logger.warning(f"embedding 计算失败，将回退分词检索: {e}")
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。任一为空或零向量返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
