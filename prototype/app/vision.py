"""视觉识别层：把一张照片变成结构化的物品清单。

设计要点：
1. 识别与引导解耦。识别层只负责"画面里有什么"，不判断属于哪类垃圾；
   类别判定交给规则库（app/disassembler.py），因为分类结论高度依赖地区标准与条件，
   属于确定性问题，不适合让模型自由发挥。
2. 三种后端同一接口：mock（离线预置场景）/ multimodal（多模态大模型 API）。
   没有 API Key 时用 mock 跑通流程与录制演示脚本。
3. 强制结构化输出。提示词要求模型只返回 JSON，解析失败时保留原始文本便于排障。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx
import yaml


@dataclass
class DetectedItem:
    name: str
    material: str = ""
    confidence: float = 0.0


@dataclass
class VisionResult:
    summary: str
    items: list[DetectedItem] = field(default_factory=list)
    backend: str = ""
    latency_ms: float = 0.0
    scenario_id: str = ""
    raw: str = ""
    note: str = ""

    def item_names(self) -> list[str]:
        return [item.name for item in self.items]


class VisionBackend(Protocol):
    name: str

    def health(self) -> tuple[bool, str]:
        ...

    def analyze(self, image_path: str | None, hint: str = "") -> VisionResult:
        ...


# ============================================================
# 离线预置场景（mock）
# ============================================================


class MockVisionBackend:
    """按文件名或下拉选择返回预置的识别结果，用于跑通流程与录制演示脚本。

    输出会明确标注为模拟结果，避免被误当作真实识别效果写进参赛材料。
    """

    name = "mock-vision"

    def __init__(self, scenario_path: Path) -> None:
        self.scenario_path = scenario_path
        self.scenarios: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.scenario_path.exists():
            self.scenarios = {}
            return
        payload = yaml.safe_load(self.scenario_path.read_text(encoding="utf-8")) or {}
        self.scenarios = dict(payload.get("scenarios") or {})

    def options(self) -> list[tuple[str, str]]:
        """返回 [(label, id)]，供界面下拉使用。"""
        return [
            (f"{raw.get('label', key)}", key) for key, raw in self.scenarios.items()
        ]

    def match_by_filename(self, image_path: str | None) -> str:
        if not image_path:
            return ""
        stem = Path(image_path).stem
        for key, raw in self.scenarios.items():
            keywords = [key, str(raw.get("label", ""))] + list(raw.get("aliases") or [])
            if any(word and word in stem for word in keywords):
                return key
        return ""

    def health(self) -> tuple[bool, str]:
        count = len(self.scenarios)
        return True, f"离线预置场景 {count} 个（不调用外部模型）"

    def analyze(self, image_path: str | None, hint: str = "") -> VisionResult:
        started = time.perf_counter()
        scenario_id = hint or self.match_by_filename(image_path)
        if scenario_id not in self.scenarios:
            scenario_id = next(iter(self.scenarios), "")

        if not scenario_id:
            return VisionResult(
                summary="未配置离线场景，无法给出模拟识别结果。",
                backend=self.name,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                note="请检查 data/vision_scenarios.yaml",
            )

        raw = self.scenarios[scenario_id]
        items = [
            DetectedItem(
                name=str(entry.get("name", "")),
                material=str(entry.get("material", "")),
                confidence=float(entry.get("confidence", 0.0)),
            )
            for entry in (raw.get("items") or [])
        ]
        matched_by_filename = bool(self.match_by_filename(image_path))
        note = "模拟识别结果，未调用视觉模型"
        if image_path and not matched_by_filename:
            note += "；当前图片文件名未匹配到场景，使用了下拉选择的结果"
        return VisionResult(
            summary=str(raw.get("summary", "")),
            items=items,
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            scenario_id=scenario_id,
            raw=json.dumps(raw, ensure_ascii=False),
            note=note,
        )


# ============================================================
# 多模态大模型（OpenAI 兼容 /chat/completions + image_url）
# ============================================================

VISION_PROMPT = """你是垃圾分类投放引导系统的识别模块。
请仔细观察图片，列出画面中**所有需要分别投放的部件**。

要求：
1. 复合物品必须拆成部件逐一列出（例如奶茶要拆成：杯身、杯盖、吸管、剩余液体）；
2. 每个部件给出材质或形态（例如 PP 塑料、纸、液体、食物残渣）；
3. **名称必须用通用的物品名，不要用描述性长句**。
   正确示例：塑料瓶、易拉罐、纸板箱、塑料袋、泡沫块、木材、金属罐、织物碎片、玻璃瓶。
   错误示例：透明PET瓶身残件、银色波纹金属管状物体、黄色圆筒状疑似容器。
   同一类物品多次出现时用同一个名称重复列出即可，不要为了区分而改名。
4. 只描述你确实看到的内容，不确定的不要编造；
5. 严格只输出 JSON，不要输出任何解释文字或代码块标记。

输出格式：
{"summary": "一句话描述画面", "items": [{"name": "部件名称", "material": "材质", "confidence": 0.9}]}"""


class MultimodalVisionBackend:
    """调用 OpenAI 兼容的多模态接口（通义千问-VL / 智谱 GLM-4V / GPT-4o 等）。"""

    name = "multimodal"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 90,
        thinking: str = "",
        json_mode: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # DeepSeek 系模型支持 thinking 开关；其它供应商留空即可，
        # 留空时不会往请求体里塞这个字段。
        self.thinking = thinking.strip().lower()
        # 打开后要求接口强制返回合法 JSON（DeepSeek / OpenAI 等支持 response_format）
        self.json_mode = bool(json_mode)
        self.name = f"multimodal:{model}"

    def health(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 VISION_API_KEY"
        return True, f"已配置视觉模型 {self.model}"

    @staticmethod
    def encode_image(image_path: str) -> tuple[str, str]:
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return mime, data

    def analyze(self, image_path: str | None, hint: str = "") -> VisionResult:
        if not image_path:
            return VisionResult(
                summary="未提供图片。", backend=self.name, note="请先上传或拍摄一张照片"
            )

        mime, encoded = self.encode_image(image_path)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
        }
        if self.thinking:
            payload["thinking"] = {"type": self.thinking}
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        # 模型偶尔会吐出不合法 JSON（实测出现过一次），失败就原样再问一次。
        started = time.perf_counter()
        content = ""
        parsed: dict = {}
        parse_note = ""
        for attempt in range(2):
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
            content = (
                (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
            )
            parsed, parse_note = parse_vision_json(content)
            if parsed.get("items"):
                if attempt:
                    parse_note = (parse_note + "；第 2 次请求解析成功").strip("；")
                break
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        items = [
            DetectedItem(
                name=str(entry.get("name", "")).strip(),
                material=str(entry.get("material", "")).strip(),
                confidence=float(entry.get("confidence", 0.0) or 0.0),
            )
            for entry in (parsed.get("items") or [])
            if str(entry.get("name", "")).strip()
        ]
        return VisionResult(
            summary=str(parsed.get("summary", "")).strip(),
            items=items,
            backend=self.name,
            latency_ms=latency_ms,
            raw=content,
            note=parse_note,
        )


def parse_vision_json(content: str) -> tuple[dict, str]:
    """尽量从模型输出里抽出 JSON；失败时返回空结构并给出说明。"""
    text = (content or "").strip()
    if not text:
        return {}, "模型返回为空"

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text), ""
    except json.JSONDecodeError:
        pass

    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0)), ""
        except json.JSONDecodeError:
            pass
    return {}, "模型输出不是合法 JSON，已保留原始文本供排障"


def build_vision_backend(settings) -> VisionBackend:
    if settings.resolved_vision_backend == "multimodal":
        return MultimodalVisionBackend(
            base_url=settings.vision_base_url,
            api_key=settings.vision_api_key,
            model=settings.vision_model,
            timeout=settings.vision_timeout,
            thinking=getattr(settings, "vision_thinking", ""),
            json_mode=getattr(settings, "vision_json_mode", False),
        )
    return MockVisionBackend(settings.vision_scenarios_path)
