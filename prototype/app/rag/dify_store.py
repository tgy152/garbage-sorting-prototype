"""Dify 数据集检索（APP_MODE=dify 时启用）。"""

from __future__ import annotations

import httpx

from app.schemas import Chunk, Retrieved


class DifyRetriever:
    def __init__(self, api_base: str, api_key: str, dataset_id: str, timeout: int = 30) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.dataset_id = dataset_id
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        if not self.api_key or not self.dataset_id:
            return False, "未配置 DIFY_API_KEY / DIFY_DATASET_ID"
        try:
            response = httpx.get(
                f"{self.api_base}/datasets/{self.dataset_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                return True, "Dify 数据集连接正常"
            return False, f"Dify 返回 {response.status_code}：{response.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            return False, f"无法连接 Dify：{exc}"

    def search(self, query: str, top_k: int, threshold: float) -> list[Retrieved]:
        response = httpx.post(
            f"{self.api_base}/datasets/{self.dataset_id}/retrieve",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "retrieval_model": {
                    "search_method": "hybrid_search",
                    "reranking_enable": False,
                    "top_k": top_k,
                    "score_threshold": threshold,
                    "score_threshold_enabled": threshold > 0,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        results: list[Retrieved] = []
        for record in response.json().get("records", []):
            segment = record.get("segment", {}) or {}
            document = segment.get("document", {}) or {}
            text = (segment.get("content") or "").strip()
            if not text:
                continue
            results.append(
                Retrieved(
                    chunk=Chunk(
                        chunk_id=str(segment.get("id", "")),
                        doc_id=str(document.get("id", "")),
                        doc_title=str(document.get("name") or "未命名文档"),
                        source=str(document.get("name") or "dify"),
                        text=text,
                    ),
                    score=float(record.get("score") or 0.0),
                )
            )
        return results
