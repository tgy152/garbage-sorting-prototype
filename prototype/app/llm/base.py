"""后端统一接口与工厂。

三个后端实现同一份 Protocol，所以切换 APP_MODE 时上层 service / ui 完全无感。
这一点是方案书里「技术路线合理、模块可替换」的实证。
"""

from __future__ import annotations

from typing import Protocol

from app.schemas import LLMResult


class LLMBackend(Protocol):
    name: str

    def health(self) -> tuple[bool, str]:
        """返回 (是否可用, 说明文字)，供界面顶部的状态栏显示。"""

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> LLMResult:
        ...


def build_backend(settings) -> LLMBackend:
    backend = settings.resolved_llm_backend
    if backend == "openai":
        from app.llm.openai_compat import OpenAICompatBackend

        return OpenAICompatBackend(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            thinking=getattr(settings, "llm_thinking", ""),
        )
    if backend == "dify":
        from app.llm.dify_chat import DifyChatBackend

        return DifyChatBackend(
            api_base=settings.dify_api_base,
            api_key=settings.dify_api_key,
            timeout=settings.llm_timeout,
        )
    from app.llm.mock import MockBackend

    return MockBackend()
