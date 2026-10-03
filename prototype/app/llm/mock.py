"""离线模拟后端：不调用任何外部服务，用于先跑通界面、录制演示视频脚本。"""

from __future__ import annotations

import re
import time

from app.schemas import LLMResult


class MockBackend:
    """把检索到的上下文原样整理成结构化回答。

    输出明确标注 MOCK，避免演示时被误当作真实模型效果写进参赛材料。
    """

    name = "mock"

    def health(self) -> tuple[bool, str]:
        return True, "离线模拟模式（不调用外部模型）"

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
    ) -> LLMResult:
        started = time.perf_counter()
        context = self._extract_context(system_prompt)
        question = user_message.strip()

        if not context or context.strip() == "（无）":
            answer = (
                f"【模拟输出 MOCK】\n\n"
                f"关于「{question}」，知识库中没有检索到相关条目，无法给出可靠答复。\n\n"
                "建议：补充相关规范文档到知识库后重试，或咨询本项目所属场景的主管部门。"
            )
        else:
            items = self._pick_items(context, question)
            lines = [
            "【模拟输出 MOCK：未调用真实大模型】",
                "",
                "**结论**：已从知识库中检索到与此问题直接相关的条款，整理如下。",
                "",
                "**依据**：",
            ]
            lines.extend(f"{idx}. {item}" for idx, item in enumerate(items, start=1))
            lines.extend(
                [
                    "",
                    "**操作建议**：按上述条款逐项核对；若现场情况与条款不一致，"
                    "以本地现行规定为准。",
                ]
            )
            answer = "\n".join(lines)

        return LLMResult(
            text=answer,
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage={"note": "mock"},
        )

    @staticmethod
    def _extract_context(system_prompt: str) -> str:
        match = re.search(
            r"【知识库检索结果】\s*(.*?)\s*【检索结果结束】", system_prompt, re.DOTALL
        )
        return match.group(1) if match else ""

    @staticmethod
    def _pick_items(context: str, question: str) -> list[str]:
        """按问题关键词给条款打个粗排，取前 5 条，让模拟输出看起来"有依据"。"""
        lines = [
            re.sub(r"^\s*(\d+[.、]|[-·])\s*", "", line).strip()
            for line in context.splitlines()
            if re.match(r"^\s*(\d+[.、]|[-·])\s*\S", line)
        ]
        lines = [line for line in lines if line]
        if not lines:
            lines = [line.strip() for line in context.splitlines() if line.strip()][:5]

        keywords = set(re.findall(r"[\u4e00-\u9fff]{2}", question))
        scored = []
        for line in lines:
            hits = sum(1 for keyword in keywords if keyword in line)
            scored.append((hits, line))
        scored.sort(key=lambda item: -item[0])
        picked = [line for _, line in scored[:5]]
        return picked or lines[:5]
