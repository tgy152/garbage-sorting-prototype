"""本地知识索引：默认 TF-IDF（纯离线），配置了 EMBEDDING_* 时升级为向量检索。

设计取舍：
- TF-IDF 版本零依赖、零网络，保证 demo 在任何机器上都能跑；
- 中文用「单字 + 双字二元组」切词，不引入 jieba，在规范类短文本上够用；
- 向量化版本走 OpenAI 兼容的 /embeddings 接口，国产模型普遍支持。
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import httpx
import numpy as np

from app.rag.chunker import build_chunks, list_documents
from app.schemas import Chunk, Retrieved

ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")

# 通用疑问词与功能词。它们在几乎所有中文文档里都出现，若参与打分会把
# 「今天中午吃什么」「世界杯冠军是谁」这类无关问题抬到中等分数
# （实测 0.23~0.24，高于拒答门槛），必须过滤。
STOPWORDS = {
    "什么", "有什", "为什", "怎么", "么样", "怎样", "如何", "哪些", "哪个",
    "可以", "需要", "应该", "一下", "我们", "你们", "他们", "这个", "那个",
    "这些", "那些", "今天", "明天", "昨天", "中午", "早上", "晚上", "是谁",
    "不是", "就是", "还是", "或者", "因为", "所以", "但是", "如果", "那么",
    "这样", "那样", "一些", "一个", "以及", "并且", "而且", "都有", "没有",
    "知道", "请问", "帮我", "我的", "你的", "他的", "多少", "多大", "多久",
    "地方", "时候", "现在", "附近", "推荐", "一家", "关于",
    # 追加：实测发现"有没""是否"这类功能词二元组会制造虚假高分
    # （「今天下午有没有篮球赛？」曾因此拿到 0.2488 分而被误答）
    "有没", "是不", "是否", "哪一", "哪个", "哪里", "哪儿", "哪些", "几个",
    "多长", "何时", "几时", "上午", "下午", "今年", "去年", "明年", "好喝",
    "好吃", "值得", "告诉", "介绍", "怎么样", "什么样", "为什么", "什么样",
}


def tokenize(text: str) -> list[str]:
    """中文双字二元组 + 整段 + 英文数字单词，过滤通用疑问词。"""
    tokens: list[str] = [
        word for word in ASCII_WORD.findall(text.lower()) if word not in STOPWORDS
    ]
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            if run not in STOPWORDS:
                tokens.append(run)
        else:
            for i in range(len(run) - 1):
                bigram = run[i : i + 2]
                if bigram not in STOPWORDS:
                    tokens.append(bigram)
        if run not in STOPWORDS:
            tokens.append(run)
    return tokens


def _tfidf_matrix(token_lists: list[list[str]]) -> tuple[np.ndarray, dict[str, int], np.ndarray]:
    document_freq: Counter[str] = Counter()
    for tokens in token_lists:
        document_freq.update(set(tokens))
    vocab = {term: idx for idx, term in enumerate(sorted(document_freq))}
    n_docs = max(1, len(token_lists))
    idf = np.array(
        [math.log((1 + n_docs) / (1 + document_freq[term])) + 1.0 for term in vocab],
        dtype=np.float32,
    )
    matrix = np.zeros((len(token_lists), len(vocab)), dtype=np.float32)
    for row, tokens in enumerate(token_lists):
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        for term, count in counts.items():
            matrix[row, vocab[term]] = (count / total) * idf[vocab[term]]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms, vocab, idf


class EmbeddingClient:
    """OpenAI 兼容的 /embeddings 客户端（通义、智谱、SiliconFlow 均适用）。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> np.ndarray | None:
        if not texts:
            return None
        try:
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": texts},
                timeout=self.timeout,
            )
            response.raise_for_status()
            records = response.json().get("data", [])
            vectors = [item["embedding"] for item in sorted(records, key=lambda d: d["index"])]
            return np.array(vectors, dtype=np.float32)
        except Exception:
            # 向量化失败不应中断演示，静默降级到 TF-IDF
            return None


class LocalIndex:
    """一个场景对应一份索引文件，可随时重建。"""

    def __init__(self, scene_id: str, index_path: Path) -> None:
        self.scene_id = scene_id
        self.index_path = index_path
        self.chunks: list[Chunk] = []
        self.meta: dict[str, object] = {}
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray = np.zeros(0, dtype=np.float32)
        self._matrix: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._embeddings: np.ndarray | None = None

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def build(
        self,
        kb_dir: Path,
        chunk_size: int,
        chunk_overlap: int,
        embedding_client: EmbeddingClient | None = None,
    ) -> dict[str, object]:
        started = time.perf_counter()
        self.chunks = build_chunks(kb_dir, chunk_size, chunk_overlap)

        if not self.chunks:
            self._matrix = np.zeros((0, 0), dtype=np.float32)
            self._vocab, self._idf = {}, np.zeros(0, dtype=np.float32)
            self._embeddings = None
            self.meta = {"chunks": 0, "documents": 0, "embedding": None}
            self.save()
            return self.meta

        self._matrix, self._vocab, self._idf = _tfidf_matrix(
            [tokenize(c.text) for c in self.chunks]
        )

        embedding_model = None
        self._embeddings = None
        if embedding_client is not None:
            vectors = embedding_client.embed([c.text for c in self.chunks])
            if vectors is not None and len(vectors) == len(self.chunks):
                self._embeddings = _l2_normalize(vectors)
                embedding_model = embedding_client.model

        self.meta = {
            "chunks": len(self.chunks),
            "documents": len(list_documents(kb_dir)),
            "embedding": embedding_model,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "build_seconds": round(time.perf_counter() - started, 3),
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()
        return self.meta

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scene_id": self.scene_id,
            "meta": self.meta,
            "chunks": [c.__dict__ for c in self.chunks],
            "vocab": self._vocab,
            "idf": self._idf.tolist(),
            "embeddings": None if self._embeddings is None else self._embeddings.tolist(),
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, scene_id: str, index_path: Path) -> LocalIndex | None:
        if not index_path.exists():
            return None
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        index = cls(scene_id, index_path)
        index.meta = payload.get("meta", {})
        index.chunks = [Chunk(**raw) for raw in payload.get("chunks", [])]
        index._vocab = {k: int(v) for k, v in (payload.get("vocab") or {}).items()}
        index._idf = np.array(payload.get("idf") or [], dtype=np.float32)
        index._matrix = _rebuild_matrix(index.chunks, index._vocab, index._idf)
        raw_embeddings = payload.get("embeddings")
        index._embeddings = (
            None if raw_embeddings is None else np.array(raw_embeddings, dtype=np.float32)
        )
        return index

    def search(
        self,
        query: str,
        top_k: int,
        threshold: float,
        embedding_client: EmbeddingClient | None = None,
    ) -> list[Retrieved]:
        if self.is_empty:
            return []

        scores: np.ndarray | None = None
        if embedding_client is not None and self._embeddings is not None:
            query_vector = embedding_client.embed([query])
            if query_vector is not None and len(query_vector) == 1:
                normalized = _l2_normalize(query_vector)[0]
                scores = self._embeddings @ normalized

        if scores is None:
            query_vector = np.zeros(len(self._vocab), dtype=np.float32)
            for term in tokenize(query):
                column = self._vocab.get(term)
                if column is not None:
                    query_vector[column] += self._idf[column]
            norm = float(np.linalg.norm(query_vector))
            scores = (
                self._matrix @ (query_vector / norm)
                if norm > 0
                else np.zeros(len(self.chunks), dtype=np.float32)
            )

        order = np.argsort(-scores)[: max(top_k, 1)]
        results: list[Retrieved] = []
        for position in order:
            score = float(scores[int(position)])
            if score < threshold:
                continue
            results.append(Retrieved(chunk=self.chunks[int(position)], score=score))
        return results


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _rebuild_matrix(
    chunks: list[Chunk], vocab: dict[str, int], idf: np.ndarray
) -> np.ndarray:
    """索引只持久化 vocab 与 idf，TF-IDF 向量在载入时按同一权重重建，保证分数可比。"""
    matrix = np.zeros((len(chunks), len(vocab)), dtype=np.float32)
    for row, chunk in enumerate(chunks):
        counts = Counter(tokenize(chunk.text))
        total = sum(counts.values()) or 1
        for term, count in counts.items():
            column = vocab.get(term)
            if column is not None:
                matrix[row, column] = (count / total) * idf[column]
    return _l2_normalize(matrix)
