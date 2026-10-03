"""把视觉模型配置从已安装的视觉技能同步到本项目的 .env。

用途：让原型能直接调用真实多模态模型识别照片，而不是只跑离线预置场景。
只做本地文件之间的搬运，**不会回显密钥内容**。

用法：
    python scripts/sync_vision_key.py
    python scripts/sync_vision_key.py --source "D:\\别的路径\\.env"
"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SOURCE = Path.home() / ".codex" / "skills" / "claude-vision-skill" / ".env"

KEY_MAP = {
    "DASHSCOPE_API_KEY": "VISION_API_KEY",
    "VISION_MODEL": "VISION_MODEL",
    "DASHSCOPE_BASE_URL": "VISION_BASE_URL",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def upsert(target: Path, updates: dict[str, str]) -> tuple[int, int]:
    """返回 (更新条数, 新增条数)。"""
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    seen: set[str] = set()
    updated = added = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            lines[index] = f"{key}={updates[key]}"
            seen.add(key)
            updated += 1

    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
            added += 1

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return updated, added


def mask(value: str) -> str:
    if not value:
        return "（空）"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}（长度 {len(value)}）"


def main() -> int:
    parser = argparse.ArgumentParser(description="同步视觉模型配置到 .env")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="来源 .env 路径")
    parser.add_argument("--target", default=str(PROJECT_ROOT / ".env"), help="目标 .env 路径")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        print(f"❌ 找不到来源配置：{source}")
        print("   请确认视觉技能已安装，或用 --source 指定路径。")
        return 1
    if not target.exists():
        example = target.with_name(".env.example")
        if example.exists():
            target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[sync] 已从 .env.example 生成 {target.name}")
        else:
            print(f"❌ 目标 .env 不存在且没有 .env.example：{target}")
            return 1

    source_values = read_env(source)
    updates = {
        local: source_values[remote]
        for remote, local in KEY_MAP.items()
        if source_values.get(remote)
    }
    if not updates:
        print("❌ 来源配置里没有找到可同步的键（DASHSCOPE_API_KEY / VISION_MODEL / DASHSCOPE_BASE_URL）")
        return 1

    # 视觉后端固定为真实多模态模型
    updates["VISION_BACKEND"] = "multimodal"

    updated, added = upsert(target, updates)
    print(f"[sync] 已更新 {updated} 项、新增 {added} 项到 {target}")
    for key, value in updates.items():
        shown = mask(value) if "KEY" in key else value
        print(f"    {key} = {shown}")
    print()
    print("下一步：python scripts/batch_photos.py --folder <照片目录>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
