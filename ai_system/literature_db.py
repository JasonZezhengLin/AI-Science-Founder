"""
共享文献库。

存储生态内产生的所有论文（已发表和未发表），
提供检索接口供 Semantic Scholar 工具合并返回。
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LiteratureEntry:
    """单篇文献条目。"""

    def __init__(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        authors: List[str],
        status: str,  # "published" | "rejected"
        founder_id: str,
        timestamp: Optional[str] = None,
        paper_text: str = "",
        pdf_path: Optional[str] = None,
        text_path: Optional[str] = None,
        artifact_paths: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
    ):
        self.paper_id = paper_id
        self.title = title
        self.abstract = abstract
        self.authors = authors
        self.status = status
        self.founder_id = founder_id
        self.timestamp = timestamp or datetime.now().isoformat()
        self.paper_text = paper_text
        self.pdf_path = pdf_path
        self.text_path = text_path
        self.artifact_paths = artifact_paths or []
        # 语义检索用向量（标题+摘要算的）；可能为 None（embedding 不可用时）
        self.embedding = embedding

    def embed_text(self) -> str:
        """用于算 embedding 的代表性文本：标题 + 摘要。"""
        return f"{self.title}\n{self.abstract}".strip()

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "status": self.status,
            "founder_id": self.founder_id,
            "timestamp": self.timestamp,
            "paper_text": self.paper_text,
            "pdf_path": self.pdf_path,
            "text_path": self.text_path,
            "artifact_paths": self.artifact_paths,
            "embedding": self.embedding,
            "source": "ecosystem",
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LiteratureEntry":
        return cls(
            paper_id=d["paper_id"],
            title=d.get("title", ""),
            abstract=d.get("abstract", ""),
            authors=d.get("authors", []),
            status=d.get("status", "under_review"),
            founder_id=d.get("founder_id", "unknown"),
            timestamp=d.get("timestamp"),
            paper_text=d.get("paper_text", ""),
            pdf_path=d.get("pdf_path"),
            text_path=d.get("text_path"),
            artifact_paths=d.get("artifact_paths", []),
            embedding=d.get("embedding"),
        )


class LiteratureDB:
    """
    共享文献库（内存存储，debug 版不复用 LLM 调用）。

    所有论文——无论接收或拒稿——都存入此库。
    检索时默认返回系统内所有论文，含 under_review / rejected。
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._papers: Dict[str, LiteratureEntry] = {}
        self._counter = 0
        self._persist_path = persist_path
        if persist_path:
            self._load()

    def _load(self):
        """从磁盘加载已有文献库（断点续传 / 跨进程共享）。"""
        import json
        import os
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._counter = data.get("counter", 0)
            for pid, pd in data.get("papers", {}).items():
                self._papers[pid] = LiteratureEntry.from_dict(pd)
            logger.info(
                f"LiteratureDB: 从 {self._persist_path} 加载 {len(self._papers)} 篇论文（断点续传）"
            )
        except Exception as e:
            logger.warning(f"LiteratureDB 加载失败（从空库开始）: {e}")

    def _persist(self):
        """落盘。每次 add/update 后调用，保证进程被 kill 也不丢。"""
        import json
        import os
        if not self._persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            tmp = self._persist_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "counter": self._counter,
                        "papers": {pid: e.to_dict() for pid, e in self._papers.items()},
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp, self._persist_path)  # 原子替换
        except Exception as e:
            logger.warning(f"LiteratureDB 落盘失败: {e}")

    def add_paper(
        self,
        title: str,
        abstract: str,
        authors: List[str],
        status: str,
        founder_id: str,
        paper_text: str = "",
        pdf_path: Optional[str] = None,
        text_path: Optional[str] = None,
        artifact_paths: Optional[List[str]] = None,
    ) -> str:
        """添加论文，返回 paper_id。"""
        self._counter += 1
        paper_id = f"eco_{self._counter}"
        entry = LiteratureEntry(
            paper_id=paper_id,
            title=title,
            abstract=abstract,
            authors=authors,
            status=status,
            founder_id=founder_id,
            paper_text=paper_text,
            pdf_path=pdf_path,
            text_path=text_path,
            artifact_paths=artifact_paths,
        )
        self._papers[paper_id] = entry
        # 入库时算一次 embedding（标题+摘要），供语义检索；失败则留 None 走分词兜底
        try:
            from ai_system.literature_embedding import get_embedding
            entry.embedding = get_embedding(entry.embed_text())
        except Exception as e:
            logger.warning(f"add_paper embedding 失败: {e}")
            entry.embedding = None
        logger.info(
            f"LiteratureDB: 添加论文 [{paper_id}] \"{title[:60]}...\" ({status})"
        )
        self._persist()
        return paper_id

    def update_paper(
        self,
        paper_id: str,
        *,
        status: Optional[str] = None,
        abstract: Optional[str] = None,
        paper_text: Optional[str] = None,
        pdf_path: Optional[str] = None,
        text_path: Optional[str] = None,
        artifact_paths: Optional[List[str]] = None,
    ) -> bool:
        entry = self._papers.get(paper_id)
        if entry is None:
            return False
        if status is not None:
            entry.status = status
        if abstract is not None:
            entry.abstract = abstract
        if paper_text is not None:
            entry.paper_text = paper_text
        if pdf_path is not None:
            entry.pdf_path = pdf_path
        if text_path is not None:
            entry.text_path = text_path
        if artifact_paths is not None:
            entry.artifact_paths = artifact_paths
        # 摘要变了，embedding 失效，重算（标题+摘要）
        if abstract is not None:
            try:
                from ai_system.literature_embedding import get_embedding
                entry.embedding = get_embedding(entry.embed_text())
            except Exception:
                pass
        self._persist()
        return True

    def search(self, query: str, top_k: int = 5, include_unpublished: bool = True) -> List[dict]:
        """
        语义检索（embedding 优先，分词兜底）。

        优先用 embedding 余弦相似度：能匹配近义/跨词表达（如 query 说 sharpness、
        论文写 flatness 也能命中），比纯字面匹配强。当 embedding 不可用（接口失败、
        库里论文没存向量、或 LITERATURE_EMBED=0）时，回退到分词+词重叠打分。
        """
        candidates = [
            p for p in self._papers.values()
            if include_unpublished or p.status == "published"
        ]
        if not candidates:
            return []

        # ---- 优先：embedding 语义检索 ----
        try:
            from ai_system.literature_embedding import (
                embedding_enabled, get_embedding, cosine_similarity,
            )
            if embedding_enabled():
                q_vec = get_embedding(query)
                if q_vec is not None:
                    scored = []
                    for paper in candidates:
                        vec = paper.embedding
                        if vec is None:
                            # 该论文还没向量，临时补算（不落盘，避免检索路径写盘）
                            vec = get_embedding(paper.embed_text())
                        if vec is not None:
                            sim = cosine_similarity(q_vec, vec)
                            if sim > 0:
                                scored.append((sim, paper))
                    if scored:
                        scored.sort(key=lambda x: x[0], reverse=True)
                        return [p.to_dict() for _, p in scored[:top_k]]
                    # embedding 跑了但全 0（异常），继续走分词兜底
        except Exception as e:
            logger.warning(f"embedding 检索失败，回退分词: {e}")

        # ---- 兜底：分词 + 词重叠打分 ----
        return self._search_token(query, top_k, candidates)

    def _search_token(self, query: str, top_k: int, candidates) -> List[dict]:
        """分词 + 词重叠加权打分（embedding 不可用时的兜底）。"""
        import re as _re

        def _tokens(text: str):
            return set(_re.findall(r"[a-z0-9]+", text.lower()))

        query_tokens = {t for t in _tokens(query) if len(t) > 2}
        if not query_tokens:
            return []

        scored = []
        for paper in candidates:
            title_tokens = _tokens(paper.title)
            abstract_tokens = _tokens(paper.abstract)
            body_tokens = _tokens(paper.paper_text)
            author_tokens = _tokens(paper.founder_id)
            # 加权：标题命中 ×3，摘要 ×2，全文/作者 ×1
            score = (
                3 * len(query_tokens & title_tokens)
                + 2 * len(query_tokens & abstract_tokens)
                + 1 * len(query_tokens & body_tokens)
                + 1 * len(query_tokens & author_tokens)
            )
            if score > 0:
                scored.append((score, paper))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p.to_dict() for _, p in scored[:top_k]]

    def get_paper(self, paper_id: str) -> Optional[dict]:
        entry = self._papers.get(paper_id)
        return entry.to_dict() if entry else None

    def stats(self) -> dict:
        published = sum(1 for p in self._papers.values() if p.status == "published")
        rejected = sum(1 for p in self._papers.values() if p.status == "rejected")
        under_review = sum(1 for p in self._papers.values() if p.status == "under_review")
        return {
            "total": len(self._papers),
            "published": published,
            "under_review": under_review,
            "rejected": rejected,
        }


# 全局单例
_literature_db: Optional[LiteratureDB] = None


def _default_persist_path() -> Optional[str]:
    import os
    # 默认落盘路径，可由环境变量覆盖；设为 "" 可禁用持久化（纯内存，旧行为）
    p = os.environ.get("LITERATURE_DB_PATH", "ai_system/literature_store/db.json")
    return p or None


def get_literature_db() -> LiteratureDB:
    global _literature_db
    if _literature_db is None:
        _literature_db = LiteratureDB(persist_path=_default_persist_path())
    return _literature_db


def reset_literature_db():
    global _literature_db
    _literature_db = LiteratureDB(persist_path=_default_persist_path())
