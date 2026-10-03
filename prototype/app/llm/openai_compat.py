"""OpenAI 兼容后端：DeepSeek / 通义千问 / 智谱 GLM / Kimi / OpenAI 均适用。

只改 .env 里的三行（BASE_URL / API_KEY / MODEL）就能换模型供应商，
这本身就是方案书里"技术选型解耦"的论据。
"""

from __future__ import annotations

import time

import httpx

from app.schemas import LLMResult


class OpenAICompatBackend:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.name = f"openai-compat:{model}"

    def health(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 LLM_API_KEY"
        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                return True, f"已连接 {self.base_url}"
            return False, f"服务返回 {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"无法连接：{exc}"

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> LLMResult:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in history or []:
            role = turn.get("role")
            content = turn.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return LLMResult(
            text=text or "（模型返回为空）",
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage=dict(data.get("usage") or {}),
        )
