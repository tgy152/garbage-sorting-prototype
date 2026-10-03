"""演示混投检查：指定照片拍的是哪个桶，找出不该出现在该桶里的物品。

用法：
    python scripts/check_bin.py --photo _89_ --bin kitchen
    python scripts/check_bin.py --photo _79_ --bin recyclable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.disassembler import load_disassembler  # noqa: E402
from app.vision import DetectedItem, VisionResult  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="混投检查演示")
    parser.add_argument("--photo", required=True, help="文件名包含的字符串，如 _89_")
    parser.add_argument(
        "--bin",
        default="",
        choices=["", "recyclable", "hazardous", "kitchen", "residual"],
    )
    parser.add_argument("--markdown", action="store_true", help="输出完整引导")
    args = parser.parse_args()

    settings = get_settings()
    disassembler = load_disassembler(settings.rules_dir, settings.scene_id)
    cache_path = settings.export_dir / "照片识别-缓存.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))

    matches = [name for name in cache if args.photo in name]
    if not matches:
        print(f"❌ 缓存里没有匹配 {args.photo} 的照片")
        return 1

    for name in matches:
        payload = cache[name]
        result = VisionResult(
            summary=payload.get("summary", ""),
            items=[DetectedItem(**item) for item in payload.get("items", [])],
            backend=payload.get("backend", "cache"),
        )
        guidance = disassembler.guide(result, settings.region, args.bin)
        print("=" * 70)
        print(name)
        print(f"画面：{result.summary}")
        if args.bin:
            print(f"标记为：{disassembler._category_label(settings.region, args.bin)}桶")
            print(f"混投项：{len(guidance.mismatches)} / {len(guidance.all_parts)}")
            for part in guidance.mismatches:
                print(f"  ✗ {part.display_name()} → 应投 {part.category_label}")
        else:
            print("未指定桶位，跳过混投检查")
        if args.markdown:
            print()
            print(guidance.to_markdown())
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
