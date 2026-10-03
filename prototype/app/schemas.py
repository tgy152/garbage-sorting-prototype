"""跨模块共用的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """一个知识片段。chunk_id 在方案书的"可复现性"附录里会用到。"""

    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    text: str
    ordinal: int = 0


@dataclass
class Retrieved:
    chunk: Chunk
    score: float


@dataclass
class Citation:
    doc_title: str
    source: str
    score: float
    snippet: str

    def to_markdown(self) -> str:
        return (
            f"- **{self.doc_title}**（相关度 {self.score:.2f}），"
            f"来源 `{self.source}`\n  > {self.snippet}"
        )


@dataclass
class Answer:
    """一次问答的完整结果，评测脚本依赖这里的字段。"""

    text: str
    citations: list[Citation] = field(default_factory=list)
    latency_ms: float = 0.0
    backend: str = ""
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    retrieved_ids: list[str] = field(default_factory=list)
    retrieved_text: str = ""
    usage: dict[str, object] = field(default_factory=dict)
    refused: bool = False


@dataclass
class LLMResult:
    text: str
    backend: str
    latency_ms: float
    usage: dict[str, object] = field(default_factory=dict)
