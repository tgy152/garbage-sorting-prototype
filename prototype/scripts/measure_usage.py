"""测量一次视觉识别实际消耗的 token 数量，用于估算额度能用多久。

用法：
    python scripts/measure_usage.py
    python scripts/measure_usage.py --image data/photos/xxx.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.vision import VISION_PROMPT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="测量视觉识别的 token 消耗")
    parser.add_argument("--image", default=None)
    parser.add_argument("--count", type=int, default=1, help="重复调用次数，取平均")
    args = parser.parse_args()

    settings = get_settings()
    image_path = args.image
    if image_path is None:
        photos = sorted((PROJECT_ROOT / "data" / "photos").glob("*.jpg"))
        if not photos:
            print("❌ data/photos 下没有照片")
            return 1
        image_path = str(photos[0])

    path = Path(image_path)
    if not path.exists():
        print(f"❌ 找不到图片：{path}")
        return 1

    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": settings.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
        "temperature": 0.1,
    }

    print(f"模型：{settings.vision_model}")
    print(f"图片：{path.name}（{path.stat().st_size / 1024:.0f} KB）")
    print(f"请求次数：{args.count}")
    print()

    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for index in range(args.count):
        response = httpx.post(
            f"{settings.vision_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.vision_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        usage = response.json().get("usage") or {}
        print(f"  第 {index + 1} 次：{json.dumps(usage, ensure_ascii=False)}")
        for key in totals:
            totals[key] += int(usage.get(key, 0) or 0)

    print()
    if args.count > 1:
        print("平均每次消耗：")
        divisor = args.count
        for key, value in totals.items():
            print(f"  {key}: {value / divisor:.0f}")
    else:
        print("本次消耗：")
        for key, value in totals.items():
            print(f"  {key}: {value}")

    if totals["total_tokens"]:
        print()
        print(f"按此推算，100 万 tokens 大约可识别 "
              f"{1_000_000 / (totals['total_tokens'] / args.count):.0f} 张照片")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
