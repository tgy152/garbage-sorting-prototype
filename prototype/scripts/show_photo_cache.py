"""打印照片识别缓存的内容，便于查看每张照片识别出了什么。

用法：
    python scripts/show_photo_cache.py
    python scripts/show_photo_cache.py --filter _87_ _88_
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


def main() -> int:
    parser = argparse.ArgumentParser(description="查看照片识别缓存")
    parser.add_argument("--filter", nargs="*", default=None, help="只看文件名包含这些串的记录")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()

    settings = get_settings()
    cache_path = settings.export_dir / "照片识别-缓存.json"
    if not cache_path.exists():
        print(f"❌ 没有缓存文件：{cache_path}")
        print("   先运行 python scripts/batch_photos.py --folder data/photos")
        return 1

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    for name, payload in cache.items():
        if args.filter and not any(token in name for token in args.filter):
            continue
        if args.json:
            print(json.dumps({name: payload}, ensure_ascii=False, indent=2))
            continue
        items = payload.get("items") or []
        print("=" * 70)
        print(name)
        print(f"描述：{payload.get('summary', '')}")
        print(f"部件 {len(items)} 件：")
        for item in items:
            print(f"  - {item['name']}（{item.get('material', '')}）{item.get('confidence', 0)}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
