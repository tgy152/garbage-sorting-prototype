"""场景配置加载。

这是整个骨架"可插拔"的关键：换一个场景 = 加一个 scenes/<id>.yaml +
一个 knowledge/<id>/ 目录，代码一行都不用改。
方案书里的"创新场景定义说明"可以直接由这里导出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Scene:
    scene_id: str
    name: str
    domain: str
    persona: str
    welcome: str
    system_prompt: str
    kb_dir: Path
    refusal_hint: str = "知识库中没有相关内容，建议咨询相关负责老师。"
    domain_keywords: list[str] = field(default_factory=list)
    out_of_scope_patterns: list[str] = field(default_factory=list)
    sample_questions: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    source_path: Path | None = None

    def prompt_with_context(self, context: str) -> str:
        return (
            f"{self.system_prompt.strip()}\n\n"
            "【知识库检索结果】\n"
            f"{context.strip() or '（无）'}\n"
            "【检索结果结束】\n\n"
            "请严格依据以上检索结果回答。要求：\n"
            "1. 先给结论，再给依据；\n"
            "2. 引用到具体条目时标注来源文件名；\n"
            f"3. 若检索结果无法支撑回答，直接说明「{self.refusal_hint}」，不要编造。"
        )


def _scene_paths(scenes_dir: Path) -> list[Path]:
    if not scenes_dir.exists():
        return []
    return sorted(scenes_dir.glob("*.yaml")) + sorted(scenes_dir.glob("*.yml"))


def list_scene_ids(scenes_dir: Path) -> list[str]:
    return [p.stem for p in _scene_paths(scenes_dir)]


def load_scene(scenes_dir: Path, knowledge_dir: Path, scene_id: str) -> Scene:
    path = None
    for candidate in _scene_paths(scenes_dir):
        if candidate.stem == scene_id:
            path = candidate
            break
    if path is None:
        available = list_scene_ids(scenes_dir)
        raise FileNotFoundError(
            f"找不到场景配置 scenes/{scene_id}.yaml，已有场景：{available or '（无）'}"
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kb_dir = knowledge_dir / scene_id
    kb_dir.mkdir(parents=True, exist_ok=True)

    return Scene(
        scene_id=scene_id,
        name=raw.get("name", scene_id),
        domain=raw.get("domain", ""),
        persona=raw.get("persona", "领域助手"),
        welcome=raw.get("welcome", "你好，请描述你的问题。"),
        system_prompt=raw.get("system_prompt", "你是一个严谨的领域助手。"),
        refusal_hint=raw.get("refusal_hint", "知识库中没有相关内容，建议咨询相关负责老师。"),
        domain_keywords=list(raw.get("domain_keywords") or []),
        out_of_scope_patterns=list(raw.get("out_of_scope_patterns") or []),
        sample_questions=list(raw.get("sample_questions") or []),
        users=list(raw.get("users") or []),
        pain_points=list(raw.get("pain_points") or []),
        kb_dir=kb_dir,
        source_path=path,
    )
