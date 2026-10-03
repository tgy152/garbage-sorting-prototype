"""把真实照片复制到作品页的素材目录，并输出尺寸供排版使用。

按 frontend-design / design-taste-frontend 的要求，落地页必须使用**真实图片**，
不接受用 div 拼出来的假截图。这里直接复用项目里已经采集的校园实拍照片。

用法：
    python scripts/setup_landing_assets.py
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "data" / "photos"
TARGET_DIR = PROJECT_ROOT.parent / "landing" / "assets"

# 用途 -> (源文件名片段, 目标文件名)
ASSIGNMENTS = {
    "hero": ("_89_", "hero-bin-mixed.jpg"),
    "evidence-correct": ("_79_", "evidence-recyclable-bin.jpg"),
    "evidence-hazardous": ("_81_", "evidence-battery-pile.jpg"),
    "evidence-ewaste": ("_82_", "evidence-ewaste-pile.jpg"),
}


def jpeg_size(path: Path) -> tuple[int, int]:
    """读取 JPEG 宽高，用于规划版式比例。"""
    with path.open("rb") as handle:
        handle.read(2)
        while True:
            byte = handle.read(1)
            while byte and byte != b"\xff":
                byte = handle.read(1)
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if not marker:
                return (0, 0)
            if marker[0] in range(0xC0, 0xCF) and marker[0] not in (0xC4, 0xC8, 0xCC):
                handle.read(3)
                height, width = struct.unpack(">HH", handle.read(4))
                return (width, height)
            length = struct.unpack(">H", handle.read(2))[0]
            handle.seek(length - 2, 1)


def main() -> int:
    if not SOURCE_DIR.exists():
        print(f"源照片目录不存在：{SOURCE_DIR}")
        return 1
    photos = list(SOURCE_DIR.glob("*.jpg"))
    if not photos:
        print(f"源目录没有照片：{SOURCE_DIR}")
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"源目录：{SOURCE_DIR}（{len(photos)} 张）")
    print(f"目标目录：{TARGET_DIR}")
    print()

    for role, (needle, target_name) in ASSIGNMENTS.items():
        match = next((p for p in photos if needle in p.name), None)
        if match is None:
            print(f"  ❌ {role:20} 未找到匹配 {needle} 的照片")
            continue
        target = TARGET_DIR / target_name
        shutil.copy2(match, target)
        width, height = jpeg_size(target)
        ratio = round(width / height, 3) if height else 0
        print(
            f"  ✅ {role:20} {target_name:28} "
            f"{width}x{height}  {target.stat().st_size / 1024:.0f} KB  比例 {ratio}"
        )
    print()
    print("说明：这些是项目自采的真实校园照片，不是素材库图片。")
    print("      正式提交前请确认照片中不含可识别的人员面部与个人信息。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
