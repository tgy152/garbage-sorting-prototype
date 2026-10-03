"""界面自检：构建 Gradio 界面并捕获所有警告，用于定位"页面打不开/白屏"。"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    captured: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from app.ui import build_demo

        demo = build_demo()
        for item in caught:
            captured.append(f"{item.category.__name__}: {item.message}")

    print(f"界面构建成功，组件数 {len(demo.blocks)}")
    if captured:
        print(f"\n⚠️ 捕获到 {len(captured)} 条警告：")
        for line in captured:
            print(f"  - {line}")
    else:
        print("\n✅ 无警告")
    return 1 if captured else 0


if __name__ == "__main__":
    raise SystemExit(main())
