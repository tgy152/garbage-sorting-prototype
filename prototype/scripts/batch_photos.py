"""对一批真实照片做识别 → 拆解 → 覆盖度分析。

这是补"视觉识别准确率未测"这个数据缺口的工具：
  · 用真实多模态模型识别真实照片（不是离线预置场景）；
  · 把识别结果喂给拆解引擎，产出真实的投放引导；
  · 统计**规则覆盖率** —— 识别出的部件里有多少能被规则库接住，
    未覆盖的部件会汇总成"规则补充清单"，直接指导下一轮迭代。

用法（在 prototype 目录下执行）：
    python scripts/batch_photos.py --folder data/photos
    python scripts/batch_photos.py --folder "C:\\Users\\xxx\\Desktop\\垃圾" --region shanghai
    python scripts/batch_photos.py --folder data/photos --reuse   # 复用上次识别结果，不重复调用模型
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.disassembler import load_disassembler  # noqa: E402
from app.vision import build_vision_backend  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="真实照片批量识别与规则覆盖分析")
    parser.add_argument("--folder", required=True, help="照片目录")
    parser.add_argument("--scene", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument(
        "--bin",
        default="",
        choices=["", "recyclable", "hazardous", "kitchen", "residual"],
        help="照片拍的是哪个桶，选了就做混投检查",
    )
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="复用 data/exports/照片识别-缓存.json，不重复调用视觉模型",
    )
    args = parser.parse_args()

    settings = get_settings()
    scene_id = args.scene or settings.scene_id
    region = args.region or settings.region

    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = (PROJECT_ROOT / folder).resolve()
    images = list_images(folder)
    if not images:
        print(f"❌ 目录里没有找到图片：{folder}")
        return 1

    disassembler = load_disassembler(settings.rules_dir, scene_id)
    vision = build_vision_backend(settings)

    print(f"[photos] 目录：{folder}")
    print(f"[photos] 照片：{len(images)} 张")
    print(f"[photos] 视觉后端：{vision.name}")
    ok, message = vision.health()
    print(f"[photos] 后端状态：{'✅' if ok else '❌'} {message}")
    print(f"[photos] 规则库：{disassembler.name}")
    print(f"[photos] 地区口径：{disassembler.region_name(region)}")
    print()

    export_dir = settings.export_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    cache_path = export_dir / "照片识别-缓存.json"
    cache: dict[str, dict] = {}
    if args.reuse and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"[photos] 已载入缓存 {len(cache)} 条")

    rows: list[dict] = []
    report_lines: list[str] = [
        "# 真实照片识别与投放引导报告",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 照片目录：`{folder}`",
        f"- 视觉后端：`{vision.name}`",
        f"- 规则库：{disassembler.name}（{disassembler.version}）",
        f"- 地区口径：{disassembler.region_name(region)}",
        "",
    ]

    uncovered_counter: dict[str, int] = {}
    total_items = covered_items = composite_hits = 0

    for index, image in enumerate(images, start=1):
        key = image.name
        cached = cache.get(key)
        if cached is not None:
            from app.schemas import Chunk  # noqa: F401  仅为保持导入一致性
            from app.vision import DetectedItem, VisionResult

            result = VisionResult(
                summary=cached.get("summary", ""),
                items=[DetectedItem(**item) for item in cached.get("items", [])],
                backend=cached.get("backend", vision.name),
                latency_ms=cached.get("latency_ms", 0.0),
                note="（复用缓存）",
            )
        else:
            result = vision.analyze(str(image))
            cache[key] = {
                "summary": result.summary,
                "backend": result.backend,
                "latency_ms": result.latency_ms,
                "items": [
                    {"name": item.name, "material": item.material, "confidence": item.confidence}
                    for item in result.items
                ],
            }

        guidance = disassembler.guide(result, region, args.bin)

        item_total = len(result.items)
        item_uncovered = len(guidance.unmatched)
        item_covered = item_total - item_uncovered
        total_items += item_total
        covered_items += item_covered
        composite_hits += 1 if guidance.is_composite else 0

        for item in guidance.unmatched:
            uncovered_counter[item.name] = uncovered_counter.get(item.name, 0) + 1

        flag = "✅" if item_uncovered == 0 else "⚠️"
        print(
            f"  [{index}/{len(images)}] {flag} {image.name}  "
            f"识别 {item_total} 件 / 覆盖 {item_covered} 件 / 未覆盖 {item_uncovered} 件"
        )

        rows.append(
            {
                "照片": image.name,
                "画面描述": result.summary,
                "识别部件数": item_total,
                "规则覆盖数": item_covered,
                "未覆盖数": item_uncovered,
                "是否复合垃圾": guidance.is_composite,
                "匹配到的复合类别": guidance.composite_name or "",
                "识别部件": "、".join(item.name for item in result.items),
                "未覆盖部件": "、".join(item.name for item in guidance.unmatched),
                "识别耗时(ms)": result.latency_ms,
            }
        )

        report_lines += [
            f"## {index}. {image.name}",
            "",
            f"**画面描述**：{result.summary or '—'}",
            "",
            f"**识别到 {item_total} 个部件，规则覆盖 {item_covered} 个**"
            + (f"，未覆盖 {item_uncovered} 个" if item_uncovered else ""),
            "",
            guidance.to_markdown(),
            "",
            "---",
            "",
        ]

    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    coverage = covered_items / total_items if total_items else 0.0
    summary = {
        "照片数": len(images),
        "识别部件总数": total_items,
        "规则覆盖部件数": covered_items,
        "未覆盖部件数": total_items - covered_items,
        "规则覆盖率": round(coverage, 4),
        "命中复合规则的照片数": composite_hits,
        "未覆盖物品种类数": len(uncovered_counter),
        "视觉后端": vision.name,
        "地区口径": disassembler.region_name(region),
    }

    frame = pd.DataFrame(rows)
    stem = f"照片批量识别-{scene_id}-{region}"
    detail_path = export_dir / f"{stem}-明细.csv"
    report_path = export_dir / f"{stem}-报告.md"
    summary_path = export_dir / f"{stem}-汇总.json"
    gap_path = export_dir / f"{stem}-规则补充清单.md"

    frame.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines += [
        "## 汇总",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        *(f"| {key} | {value} |" for key, value in summary.items()),
        "",
    ]
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    ranked = sorted(uncovered_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    gap_lines = [
        "# 规则补充清单（自动生成）",
        "",
        "下面是真实照片中被识别出、但**规则库尚未覆盖**的部件。",
        "按出现次数排序，建议优先补充前几项。",
        "",
        "| 未覆盖部件 | 出现次数 |",
        "| --- | --- |",
        *(f"| {name} | {count} |" for name, count in ranked),
        "",
        "补充方式：在 `rules/waste_sorting.yaml` 的 `singles` 里新增一条规则，",
        "把该部件的名称与别名填进 `keys`，并给出 `category` 与 `pitfall`。",
        "",
    ]
    gap_path.write_text("\n".join(gap_lines), encoding="utf-8")

    print()
    print("[photos] 汇总")
    for key, value in summary.items():
        print(f"  - {key}: {value}")
    print()
    if ranked:
        print("[photos] 未覆盖部件 TOP10")
        for name, count in ranked[:10]:
            print(f"  {count:>3} 次  {name}")
    print()
    print(f"[photos] 明细：{detail_path}")
    print(f"[photos] 报告：{report_path}")
    print(f"[photos] 汇总：{summary_path}")
    print(f"[photos] 规则补充清单：{gap_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
