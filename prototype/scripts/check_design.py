"""校核一份课程设计计算表（教师侧批量校核 / 学生侧自查通用）。

用法（在 prototype 目录下执行）：
    python scripts/check_design.py --input data/samples/学生计算表_示例.csv
    python scripts/check_design.py --input 我的计算表.csv --scene hvac_design_check

产出：
    data/exports/<表名>-校核明细.csv
    data/exports/<表名>-校核报告.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.checker import SEVERITY_LABEL, load_engine  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="暖通课程设计计算自洽性校核")
    parser.add_argument("--input", required=True, help="计算表 CSV 路径")
    parser.add_argument("--scene", default="hvac_design_check", help="规则库对应的场景 ID")
    parser.add_argument("--quiet", action="store_true", help="只输出汇总，不逐条打印")
    args = parser.parse_args()

    settings = get_settings()
    engine = load_engine(settings.rules_dir, args.scene)

    csv_path = Path(args.input)
    if not csv_path.is_absolute():
        csv_path = (PROJECT_ROOT / csv_path).resolve()
    if not csv_path.exists():
        print(f"❌ 找不到文件：{csv_path}")
        return 1

    frame = engine.load_csv(csv_path)
    report = engine.check_frame(frame)

    print(f"规则库：{engine.name}（{engine.version}）")
    print(f"校核文件：{csv_path.name}")
    print(
        f"房间 {report.rows_checked} 间 ｜ 校核项 {report.total_checks} ｜ "
        f"一次通过率 {report.pass_rate * 100:.1f}% ｜ "
        f"错误 {report.error_count} ｜ 警告 {report.warning_count} ｜ "
        f"错误密度 {report.error_density} 处/房间"
    )

    if report.missing_fields:
        print("\n⚠️ 以下字段缺失或异常，相关规则未参与校核：")
        for name in report.missing_fields:
            print(f"    - {name}")

    if not args.quiet:
        print("\n逐条问题：")
        for issue in report.issues:
            flag = SEVERITY_LABEL.get(issue.severity, issue.severity)
            print(f"  {flag}  [{issue.rule_id}] {issue.room_name}（{issue.room_id}）{issue.title}")
            print(f"        应有：{issue.expected}  ｜ 实际：{issue.actual}")
            if issue.suggestion:
                print(f"        建议：{issue.suggestion}")

    ranking = report.error_ranking()
    if ranking:
        print("\n错因排行（教师视角的教学重点）：")
        for rule_id, title, count in ranking:
            print(f"    {count} 次  [{rule_id}] {title}")

    out_dir = settings.export_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = csv_path.stem
    detail_path = out_dir / f"{stem}-校核明细.csv"
    report_path = out_dir / f"{stem}-校核报告.md"
    report.to_frame().to_csv(detail_path, index=False, encoding="utf-8-sig")
    report_path.write_text(report.to_markdown(), encoding="utf-8")
    print(f"\n明细：{detail_path}")
    print(f"报告：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
