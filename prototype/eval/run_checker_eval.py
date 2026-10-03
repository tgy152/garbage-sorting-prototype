"""校核器评测：用带标注的样本集检验规则引擎的查准率与查全率。

为什么需要它：参赛作品如果只展示"能跑"，评委无法判断可靠程度。
有了带 ground truth 的评测，"准确率 96%、误报率 0" 才是有说服力的证据。

用法（在 prototype 目录下执行）：
    python eval/run_checker_eval.py

产出：
    eval/out/<scene>-校核器评测.json
    eval/out/<scene>-校核器评测.csv
    eval/out/<scene>-校核器评测图.png
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

from app.checker import load_engine  # noqa: E402
from app.config import get_settings  # noqa: E402

CASES = Path(__file__).resolve().parent / "checker_cases.jsonl"


def load_cases(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


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

        labels = ["精确率\nPrecision", "召回率\nRecall", "F1", "房间级\n准确率", "误报率\nFP rate"]
        values = [
            summary["精确率"] * 100,
            summary["召回率"] * 100,
            summary["F1"] * 100,
            summary["房间级准确率"] * 100,
            summary["误报率"] * 100,
        ]
        figure, axes = plt.subplots(figsize=(8, 4.2), dpi=160)
        bars = axes.bar(
            labels, values, color=["#2f6feb", "#1a7f37", "#8250df", "#bf8700", "#cf222e"]
        )
        axes.set_ylim(0, 112)
        axes.axhline(95, color="#d0d7de", linestyle="--", linewidth=1)
        axes.set_ylabel("百分比 (%)")
        axes.set_title(f"规则引擎校核效果（{summary['样本房间数']} 间房对照样本）")
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
    parser = argparse.ArgumentParser(description="校核器评测")
    parser.add_argument("--scene", default="hvac_design_check")
    parser.add_argument("--input", default="data/samples/学生计算表_示例.csv")
    parser.add_argument("--cases", default=str(CASES))
    args = parser.parse_args()

    settings = get_settings()
    engine = load_engine(settings.rules_dir, args.scene)

    csv_path = Path(args.input)
    if not csv_path.is_absolute():
        csv_path = (PROJECT_ROOT / csv_path).resolve()
    frame = engine.load_csv(csv_path)
    report = engine.check_frame(frame)

    cases = load_cases(Path(args.cases))
    triggered: dict[str, set[str]] = {}
    for issue in report.issues:
        triggered.setdefault(issue.room_id, set()).add(issue.rule_id)

    rows = []
    true_positive = false_positive = false_negative = 0
    exact_rooms = 0
    started = time.perf_counter()

    for case in cases:
        room_id = case["room_id"]
        expected = set(case.get("expected_rules") or [])
        actual = triggered.get(room_id, set())
        tp = len(expected & actual)
        fp = len(actual - expected)
        fn = len(expected - actual)
        true_positive += tp
        false_positive += fp
        false_negative += fn
        exact = expected == actual
        exact_rooms += 1 if exact else 0
        rows.append(
            {
                "房间编号": room_id,
                "房间名称": case.get("room_name", ""),
                "期望触发规则": " ".join(sorted(expected)) or "（无）",
                "实际触发规则": " ".join(sorted(actual)) or "（无）",
                "命中": tp,
                "误报": fp,
                "漏报": fn,
                "房间级一致": exact,
                "样本说明": case.get("note", ""),
            }
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 1.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    total_expectations = true_positive + false_negative
    fp_rate = false_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0

    summary = {
        "规则库版本": engine.version,
        "样本房间数": len(cases),
        "期望触发的规则总数": total_expectations,
        "正确命中": true_positive,
        "误报": false_positive,
        "漏报": false_negative,
        "精确率": round(precision, 4),
        "召回率": round(recall, 4),
        "F1": round(f1, 4),
        "房间级准确率": round(exact_rooms / len(cases), 4) if cases else 0.0,
        "误报率": round(fp_rate, 4),
        "校核耗时(ms)": round(elapsed_ms, 1),
        "规则条数": len(engine.rules),
        "校核项次": report.total_checks,
    }

    out_dir = settings.eval_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.scene}-校核器评测"
    json_path = out_dir / f"{stem}.json"
    csv_path_out = out_dir / f"{stem}.csv"
    chart_path = out_dir / f"{stem}图.png"

    pd.DataFrame(rows).to_csv(csv_path_out, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    chart_ok = render_chart(summary, chart_path)

    print("[checker-eval] 逐房间对照")
    for row in rows:
        flag = "OK  " if row["房间级一致"] else "DIFF"
        print(
            f"  {flag} {row['房间编号']:<5} 期望 {row['期望触发规则']:<22} "
            f"实际 {row['实际触发规则']}"
        )
    print("\n[checker-eval] 指标")
    for key, value in summary.items():
        print(f"  - {key}: {value}")
    print(f"\n[checker-eval] 汇总：{json_path}")
    print(f"[checker-eval] 明细：{csv_path_out}")
    if chart_ok:
        print(f"[checker-eval] 图表：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
