"""自动化效果验证脚本 —— 直接产出方案书「测试与验证」章节需要的指标与图表。

用法（在 prototype 目录下执行）：
    python eval/run_eval.py --scene example_lab_safety
    python eval/run_eval.py --limit 5 --tag smoke

产出：
    eval/out/<scene>-<tag>-明细.csv    逐题结果，可作附件
    eval/out/<scene>-<tag>-汇总.json   指标汇总，可复现
    eval/out/<scene>-<tag>-指标图.png  可直接放进方案书/PPT
    eval/out/<scene>-<tag>-报告.md     人 readable 的报告
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.service import SceneService  # noqa: E402

DEFAULT_EVAL_SET = Path(__file__).resolve().parent / "eval_set.jsonl"


def resolve_eval_set(scene_id: str) -> Path:
    """优先使用场景专属评测集 eval/eval_set.<scene>.jsonl。"""
    specific = Path(__file__).resolve().parent / f"eval_set.{scene_id}.jsonl"
    return specific if specific.exists() else DEFAULT_EVAL_SET


def load_eval_set(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def evaluate_one(service: SceneService, record: dict) -> dict:
    answer = service.answer(record["question"])

    hit_text = answer.text
    keywords = record.get("expected_keywords") or []
    matched = [kw for kw in keywords if kw in hit_text]
    keyword_coverage = len(matched) / len(keywords) if keywords else None

    # 检索侧覆盖率：衡量"该召回的内容是否召回了"，与生成后端无关，
    # 比只看回答文本更能反映检索质量（mock 后端不会完整复述上下文）。
    matched_ctx = [kw for kw in keywords if kw in answer.retrieved_text]
    keyword_coverage_ctx = len(matched_ctx) / len(keywords) if keywords else None

    cited_sources = [citation.source for citation in answer.citations]
    expected_sources = record.get("expected_sources") or (
        [record["expected_source"]] if record.get("expected_source") else []
    )
    source_hit = None
    if expected_sources:
        source_hit = any(
            source.startswith(prefix)
            for prefix in expected_sources
            for source in cited_sources
        )

    expect_refusal = bool(record.get("expect_refusal"))
    refusal_correct = (answer.refused == expect_refusal) if expect_refusal else (
        not answer.refused
    )

    return {
        "题号": record["id"],
        "类型": record["type"],
        "问题": record["question"],
        "是否拒答": answer.refused,
        "期望拒答": expect_refusal,
        "判定正确": refusal_correct,
        "关键词命中": "".join(f"{kw} " for kw in matched).strip(),
        "关键词覆盖率": keyword_coverage,
        "检索关键词覆盖率": keyword_coverage_ctx,
        "引用命中": source_hit,
        "检索片段数": len(answer.citations),
        "检索耗时(ms)": answer.retrieval_ms,
        "生成耗时(ms)": answer.generation_ms,
        "总耗时(ms)": answer.latency_ms,
        "回答字数": len(answer.text),
        "后端": answer.backend,
        "回答": answer.text.replace("\n", " ")[:400],
    }


def summarize(frame: pd.DataFrame) -> dict:
    in_scope = frame[frame["类型"] == "in_scope"]
    out_scope = frame[frame["类型"] == "out_of_scope"]

    def ratio(series: pd.Series) -> float | None:
        series = series.dropna()
        return round(float(series.mean()), 4) if len(series) else None

    latencies = frame["总耗时(ms)"].dropna().tolist()
    summary = {
        "样本总数": int(len(frame)),
        "范围内问题数": int(len(in_scope)),
        "范围外问题数": int(len(out_scope)),
        "范围外拒答率": ratio(out_scope["是否拒答"]) if len(out_scope) else None,
        "范围内误拒答率": ratio(in_scope["是否拒答"]) if len(in_scope) else None,
        "整体判定准确率": ratio(frame["判定正确"]),
        "平均回答关键词覆盖率": ratio(in_scope["关键词覆盖率"]),
        "平均检索关键词覆盖率": ratio(in_scope["检索关键词覆盖率"]),
        "引用来源命中率": ratio(in_scope["引用命中"]),
        "平均总耗时(ms)": round(statistics.mean(latencies), 1) if latencies else None,
        "P95 总耗时(ms)": round(
            statistics.quantiles(latencies, n=20)[-1], 1
        )
        if len(latencies) >= 20
        else (round(max(latencies), 1) if latencies else None),
        "检索平均耗时(ms)": round(float(frame["检索耗时(ms)"].mean()), 1),
    }
    return summary


def render_chart(summary: dict, target: Path) -> bool:
    """输出指标图；缺字体时自动退回英文标签，避免中文变成方框。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        chinese_fonts = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"]
        chosen = next((f for f in chinese_fonts if f in available), None)
        use_chinese = chosen is not None
        if chosen:
            plt.rcParams["font.sans-serif"] = [chosen]
            plt.rcParams["axes.unicode_minus"] = False

        def label(zh: str, en: str) -> str:
            return zh if use_chinese else en

        metrics = [
            ("范围外拒答率", "Refusal rate\n(out-of-scope)", summary["范围外拒答率"]),
            ("整体判定准确率", "Overall accuracy", summary["整体判定准确率"]),
            ("回答覆盖率", "Answer coverage", summary["平均回答关键词覆盖率"]),
            ("检索覆盖率", "Retrieval coverage", summary["平均检索关键词覆盖率"]),
            ("引用命中率", "Citation hit rate", summary["引用来源命中率"]),
        ]
        labels = [label(zh, en) for zh, en, _ in metrics]
        values = [(value or 0) * 100 for _, _, value in metrics]

        figure, axes = plt.subplots(figsize=(8, 4.2), dpi=160)
        bars = axes.bar(labels, values, color=["#2f6feb", "#1a7f37", "#bf8700", "#8250df"])
        axes.set_ylim(0, 110)
        axes.axhline(90, color="#d0d7de", linestyle="--", linewidth=1)
        axes.set_ylabel("Percent (%)" if not use_chinese else "百分比 (%)")
        axes.set_title(
            f"{summary['样本总数']} questions" if not use_chinese else f"效果验证指标（共 {summary['样本总数']} 题）"
        )
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


def render_report(summary: dict, frame: pd.DataFrame) -> str:
    failures = frame[~frame["判定正确"].astype(bool)]
    lines = [
        "# 效果验证报告（自动生成）",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 样本数：{summary['样本总数']}（范围内 {summary['范围内问题数']}，范围外 {summary['范围外问题数']}）",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 数值 | 说明 |",
        "| --- | --- | --- |",
        f"| 整体判定准确率 | {summary['整体判定准确率']} | 拒答行为是否符合预期 |",
        f"| 范围外拒答率 | {summary['范围外拒答率']} | 越高说明幻觉越少 |",
        f"| 范围内误拒答率 | {summary['范围内误拒答率']} | 越低说明召回越稳 |",
        f"| 平均回答关键词覆盖率 | {summary['平均回答关键词覆盖率']} | 生成结果是否覆盖标准答案要点 |",
        f"| 平均检索关键词覆盖率 | {summary['平均检索关键词覆盖率']} | 召回内容是否包含标准答案要点 |",
        f"| 引用来源命中率 | {summary['引用来源命中率']} | 是否引用了正确文档 |",
        f"| 平均总耗时 | {summary['平均总耗时(ms)']} ms | 端到端响应 |",
        f"| P95 总耗时 | {summary['P95 总耗时(ms)']} ms | 长尾延迟 |",
        f"| 检索平均耗时 | {summary['检索平均耗时(ms)']} ms | 检索层开销 |",
        "",
        "## 未通过样本",
        "",
    ]
    if failures.empty:
        lines.append("无。")
    else:
        lines.append("| 题号 | 问题 | 期望拒答 | 实际拒答 |")
        lines.append("| --- | --- | --- | --- |")
        for _, row in failures.iterrows():
            lines.append(
                f"| {row['题号']} | {row['问题']} | {row['期望拒答']} | {row['是否拒答']} |"
            )
    lines += [
        "",
        "## 改进方向（写进方案书的「总结与展望」）",
        "",
        "- 补充负样本与边界样本，扩大评测集规模",
        "- 引入 LLM-as-judge 对生成质量做语义级评分",
        "- 对召回失败的题目分析分块粒度与阈值设置",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行效果验证评测")
    parser.add_argument("--scene", default=None, help="场景 ID，默认取 .env 中的 SCENE_ID")
    parser.add_argument("--mode", default=None, help="覆盖 APP_MODE：mock / direct / dify")
    parser.add_argument("--eval-set", default=None, help="评测集路径，默认按场景自动选择")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题")
    parser.add_argument("--tag", default=None, help="输出文件后缀，便于多次对比")
    args = parser.parse_args()

    settings = get_settings()
    if args.mode:
        settings.app_mode = args.mode
    settings.ensure_dirs()

    scene_id = args.scene or settings.scene_id
    eval_path = Path(args.eval_set) if args.eval_set else resolve_eval_set(scene_id)
    print(f"[eval] 评测集：{eval_path}")
    records = load_eval_set(eval_path)
    if args.limit:
        records = records[: args.limit]

    service = SceneService(settings, scene_id)
    status = service.status()
    print(f"[eval] 场景：{status['场景']}")
    print(f"[eval] 生成：{status['生成后端']}")
    print(f"[eval] 检索：{status['检索后端']}")
    print(f"[eval] 待测题数：{len(records)}")

    rows = []
    for index, record in enumerate(records, start=1):
        row = evaluate_one(service, record)
        rows.append(row)
        flag = "OK " if row["判定正确"] else "FAIL"
        print(f"  [{index}/{len(records)}] {flag} {row['题号']} {row['问题'][:24]}")

    frame = pd.DataFrame(rows)
    summary = summarize(frame)

    tag = args.tag or settings.app_mode
    stem = f"{scene_id}-{tag}"
    out_dir = settings.eval_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    detail_path = out_dir / f"{stem}-明细.csv"
    summary_path = out_dir / f"{stem}-汇总.json"
    chart_path = out_dir / f"{stem}-指标图.png"
    report_path = out_dir / f"{stem}-报告.md"

    frame.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(
        json.dumps(
            {"scene": scene_id, "mode": settings.app_mode, "summary": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    chart_ok = render_chart(summary, chart_path)
    report_path.write_text(render_report(summary, frame), encoding="utf-8")

    print("\n[eval] 指标汇总")
    for key, value in summary.items():
        print(f"  - {key}: {value}")
    print(f"\n[eval] 明细：{detail_path}")
    print(f"[eval] 汇总：{summary_path}")
    print(f"[eval] 报告：{report_path}")
    if chart_ok:
        print(f"[eval] 图表：{chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
