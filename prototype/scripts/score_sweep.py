"""调参用：扫描评测集里每题的最高检索分，用于标定拒答门槛。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.service import SceneService  # noqa: E402


def main() -> int:
    settings = get_settings()
    scene_id = settings.scene_id
    service = SceneService(settings, scene_id)
    assert service.index is not None

    eval_path = PROJECT_ROOT / "eval" / f"eval_set.{scene_id}.jsonl"
    if not eval_path.exists():
        eval_path = PROJECT_ROOT / "eval" / "eval_set.jsonl"

    records = [
        json.loads(line)
        for line in eval_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"评测集：{eval_path.name}（{len(records)} 题）")
    print(f"当前拒答门槛 REFUSE_MIN_SCORE = {settings.refuse_min_score}")
    print()
    header = f"{'类型':<14}{'最高分':>8}  {'命中文档':<26}{'期望':<6} 问题"
    print(header)
    print("-" * len(header))

    in_scope: list[float] = []
    out_scope: list[float] = []
    for record in records:
        hits = service.index.search(record["question"], top_k=1, threshold=0.0)
        score = hits[0].score if hits else 0.0
        source = hits[0].chunk.source if hits else "—"
        expected = record.get("expected_source") or "—"
        if record["type"] == "in_scope":
            in_scope.append(score)
            mark = "OK" if source.startswith(expected) else "MISS"
        else:
            out_scope.append(score)
            mark = "OK" if score == 0 else "RISK"
        print(
            f"{record['type']:<14}{score:>8.4f}  {source:<26}{mark:<6} {record['question']}"
        )

    print()
    if in_scope:
        print(f"范围内最低分：{min(in_scope):.4f}  最高分：{max(in_scope):.4f}")
    if out_scope:
        print(f"范围外最高分：{max(out_scope):.4f}")
    print(
        "建议：REFUSE_MIN_SCORE 取「范围内最低分」与「范围外最高分」之间，"
        "并留出余量。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
