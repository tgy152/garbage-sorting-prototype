"""拆解引导效果验证：用带 ground truth 的场景集检验拆解引擎。

覆盖六个维度：
  1. 复合物品识别准确率 —— 是否正确匹配到预期的那一类复合垃圾
  2. 部件召回率         —— 应拆出的部件是否都拆到了
  3. 类别判定准确率     —— 每个部件的投放类别是否正确
  4. 条件化提示覆盖率   —— 类别依赖条件时，是否给出了条件说明
  5. 误投提示覆盖率     —— 是否给出了该物品最常见的误投提醒
  6. 地区标签一致性     —— 切换地区后，输出中是否残留其它地区的类别叫法（回归测试）

用法（在 prototype 目录下执行）：
    python eval/run_waste_eval.py
    python eval/run_waste_eval.py --region shanghai

注意：本脚本验证的是「识别结果 → 拆解引导」这一段。
视觉识别的准确率需要用真实照片 + 多模态模型另行测量，
不能用离线预置场景的结果代替，否则属于数据不实。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.disassembler import load_disassembler  # noqa: E402
from app.vision import MockVisionBackend, build_vision_backend  # noqa: E402

CASES = Path(__file__).resolve().parent / "waste_cases.jsonl"

# 通用口径下的类别名，用于跨地区残留检查
NATIONAL_LABELS = {
    "kitchen": "厨余垃圾",
    "residual": "其他垃圾",
}

# 桶名简写也要检查，否则"厨余桶"会漏网（曾出现过的真实缺陷）
SHORTHAND_TOKENS = ["厨余桶", "其他桶"]


def load_cases(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def match_part(guidance_parts, keyword: str):
    """按关键词在部件名或识别命中项中查找对应部件。"""
    for part in guidance_parts:
        if keyword in part.part:
            return part
        if any(keyword in name for name in part.matched_items):
            return part
    return None


def render_chart(summary: dict, target: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        chosen = next(
            (f for f in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if f in available),
            None,
        )
        if chosen:
            plt.rcParams["font.sans-serif"] = [chosen]
            plt.rcParams["axes.unicode_minus"] = False

        metrics = [
            ("复合匹配", "Composite match", summary["复合物品识别准确率"]),
            ("部件召回", "Part recall", summary["部件召回率"]),
            ("类别判定", "Category accuracy", summary["类别判定准确率"]),
            ("条件提示", "Conditional hint", summary["条件化提示覆盖率"]),
            ("误投提示", "Pitfall hint", summary["误投提示覆盖率"]),
            ("地区一致", "Region consistency", summary["地区标签一致性"]),
        ]
        labels = [f"{zh}\n{en}" for zh, en, _ in metrics]
        values = [(value or 0) * 100 for _, _, value in metrics]

        figure, axes = plt.subplots(figsize=(9, 4.4), dpi=160)
        bars = axes.bar(
            labels,
            values,
            color=["#2f6feb", "#1a7f37", "#8250df", "#bf8700", "#cf222e", "#0969da"],
        )
        axes.set_ylim(0, 112)
        axes.axhline(90, color="#d0d7de", linestyle="--", linewidth=1)
        axes.set_ylabel("百分比 (%)")
        axes.set_title(f"拆解引导效果验证（{summary['样本数']} 个场景样本）")
        for bar, value in zip(bars, values):
            axes.text(
                bar.get_x() + bar.get_width() / 2,
                value + 2,
                f"{value:.1f}%",
                ha="center",
                fontsize=10,
            )
        figure.tight_layout()
        figure.savefig(target)
        plt.close(figure)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 生成图表失败：{exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="拆解引导效果验证")
    parser.add_argument("--scene", default=None)
    parser.add_argument("--region", default=None, help="覆盖 .env 中的 REGION")
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument(
        "--vision",
        default="mock",
        choices=["mock", "configured"],
        help="mock：固定用离线预置场景（默认，评测拆解引擎用）；"
        "configured：使用 .env 里配置的视觉后端",
    )
    args = parser.parse_args()

    settings = get_settings()
    scene_id = args.scene or settings.scene_id
    region = args.region or settings.region

    disassembler = load_disassembler(settings.rules_dir, scene_id)
    if args.vision == "mock":
        # 本节验证的是「识别结果 → 拆解引导」这一段，
        # 必须固定用预置场景，否则换成真实视觉模型后拿不到输入，评测会全空。
        vision = MockVisionBackend(settings.vision_scenarios_path)
    else:
        vision = build_vision_backend(settings)
    cases = load_cases(Path(args.cases))

    print(f"[waste-eval] 规则库：{disassembler.name}（{disassembler.version}）")
    print(f"[waste-eval] 地区口径：{disassembler.region_name(region)}")
    print(f"[waste-eval] 视觉后端：{vision.name}")
    print(f"[waste-eval] 样本场景：{len(cases)}")
    print()

    rows = []
    composite_hit = 0
    part_expected = part_found = part_correct = 0
    conditional_needed = conditional_ok = 0
    pitfall_needed = pitfall_ok = 0
    region_ok = region_total = 0

    for case in cases:
        result = vision.analyze(None, hint=case["scenario"])
        guidance = disassembler.guide(result, region)

        composite_ok = guidance.composite_id == case["expect_composite"]
        composite_hit += 1 if composite_ok else 0

        missing: list[str] = []
        wrong: list[str] = []
        for expected in case["expected_parts"]:
            part_expected += 1
            part = match_part(guidance.all_parts, expected["match"])
            if part is None:
                missing.append(expected["match"])
                continue
            part_found += 1
            if part.category == expected["category"]:
                part_correct += 1
            else:
                wrong.append(f"{expected['match']}:{part.category}≠{expected['category']}")

        if case.get("need_conditional"):
            conditional_needed += 1
            conditional_ok += 1 if guidance.has_conditional else 0
        if case.get("need_pitfall"):
            pitfall_needed += 1
            pitfall_ok += 1 if guidance.has_pitfall else 0

        # 地区一致性回归测试：切到非通用口径时不应残留通用类别名
        rendered = guidance.to_markdown()
        leaks = [
            label
            for key, label in NATIONAL_LABELS.items()
            if region != "national" and label != disassembler._category_label(region, key)
            and label in rendered
        ]
        if region != "national":
            leaks += [token for token in SHORTHAND_TOKENS if token in rendered]
        if region != "national":
            region_total += 1
            region_ok += 1 if not leaks else 0

        rows.append(
            {
                "题号": case["id"],
                "场景": case["label"],
                "期望复合类别": case["expect_composite"],
                "实际复合类别": guidance.composite_id or "（未匹配）",
                "复合匹配": composite_ok,
                "拆解部件数": len(guidance.all_parts),
                "漏拆部件": " ".join(missing) or "",
                "类别判错": " ".join(wrong) or "",
                "给出条件说明": guidance.has_conditional,
                "给出误投提示": guidance.has_pitfall,
                "地区标签残留": " ".join(leaks) or "",
                "样本说明": case.get("note", ""),
            }
        )

    summary = {
        "规则库版本": disassembler.version,
        "地区口径": disassembler.region_name(region),
        "样本数": len(cases),
        "复合物品识别准确率": round(composite_hit / len(cases), 4) if cases else 0.0,
        "部件召回率": round(part_found / part_expected, 4) if part_expected else 0.0,
        "类别判定准确率": round(part_correct / part_expected, 4) if part_expected else 0.0,
        "条件化提示覆盖率": round(conditional_ok / conditional_needed, 4)
        if conditional_needed
        else 1.0,
        "误投提示覆盖率": round(pitfall_ok / pitfall_needed, 4) if pitfall_needed else 1.0,
        "地区标签一致性": round(region_ok / region_total, 4) if region_total else 1.0,
        "应拆部件总数": part_expected,
        "规则库复合类别数": len(disassembler.composites),
        "规则库单品数": len(disassembler.singles),
    }

    frame = pd.DataFrame(rows)
    out_dir = settings.eval_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{scene_id}-拆解引导-{region}"
    csv_path = out_dir / f"{stem}-明细.csv"
    json_path = out_dir / f"{stem}-汇总.json"
    chart_path = out_dir / f"{stem}-指标图.png"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    chart_ok = render_chart(summary, chart_path)

    print("[waste-eval] 逐场景结果")
    for row in rows:
        flag = "OK  " if row["复合匹配"] else "DIFF"
        extra = []
        if row["漏拆部件"]:
            extra.append(f"漏拆={row['漏拆部件']}")
        if row["类别判错"]:
            extra.append(f"判错={row['类别判错']}")
        if row["地区标签残留"]:
            extra.append(f"地区残留={row['地区标签残留']}")
        print(
            f"  {flag} {row['题号']:<5}{row['场景']:<20} "
            f"部件 {row['拆解部件数']:<3} {' '.join(extra)}"
        )

    print("\n[waste-eval] 指标汇总")
    for key, value in summary.items():
        print(f"  - {key}: {value}")
    print(f"\n[waste-eval] 明细：{csv_path}")
    print(f"[waste-eval] 汇总：{json_path}")
    if chart_ok:
        print(f"[waste-eval] 图表：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
