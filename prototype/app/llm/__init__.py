"""LLM 后端：mock / openai 兼容 / dify，共用同一套接口。"""

from app.llm.base import LLMBackend, build_backend

__all__ = ["LLMBackend", "build_backend"]
