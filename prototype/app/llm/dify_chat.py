"""Dify 应用后端：调用 Dify Service API 的 chat-messages 接口。

Dify 侧已完成提示词编排与知识库检索，因此传入的 system_prompt 会被忽略
（保留参数是为了与其它后端保持同一接口）。
"""

from __future__ import annotations

import json
import time

import httpx

from app.schemas import LLMResult


class DifyChatBackend:
    def __init__(self, api_base: str, api_key: str, timeout: int = 60) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.name = "dify"

    def health(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 DIFY_API_KEY"
        try:
            response = httpx.get(
                f"{self.api_base}/parameters",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                return True, f"已连接 Dify（{self.api_base}）"
            return False, f"Dify 返回 {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"无法连接 Dify：{exc}"

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
        user_id: str = "gradio-demo",
        conversation_id: str = "",
    ) -> LLMResult:
        payload = {
            "inputs": {},
            "query": user_message,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user_id,
        }
        started = time.perf_counter()
        response = httpx.post(
            f"{self.api_base}/chat-messages",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return LLMResult(
            text=data.get("answer", ""),
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage={
                "conversation_id": data.get("conversation_id", ""),
                "message_id": data.get("message_id", ""),
                "metadata": json.dumps(data.get("metadata", {}), ensure_ascii=False),
            },
        )
