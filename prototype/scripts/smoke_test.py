"""冒烟测试：不启动界面，快速验证配置、索引与问答链路是否正常。

用法：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --scene example_lab_safety --questions 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.service import SceneService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="原型冒烟测试")
    parser.add_argument("--scene", default=None)
    parser.add_argument("--mode", default=None, help="覆盖 APP_MODE")
    parser.add_argument("--questions", type=int, default=3)
    parser.add_argument("--rebuild", action="store_true", help="强制重建索引")
    args = parser.parse_args()

    settings = get_settings()
    if args.mode:
        settings.app_mode = args.mode
    settings.ensure_dirs()

    scene_id = args.scene or settings.scene_id
    service = SceneService(settings, scene_id)

    if args.rebuild:
        print("[smoke] 重建索引…")
        print(f"[smoke] {service.rebuild_index()}")

    print("[smoke] 配置快照")
    for key, value in settings.public_summary().items():
        print(f"    {key} = {value}")

    print("[smoke] 运行时状态")
    for key, value in service.status().items():
        print(f"    {key} = {value}")

    questions = (service.scene.sample_questions or [])[: max(args.questions, 0)]
    if not questions:
        print("[smoke] 场景未配置示例问题，跳过问答测试")
        return 0

    failures = 0
    for question in questions:
        answer = service.answer(question)
        print(f"\n[smoke] Q: {question}")
        print(f"[smoke]   后端={answer.backend} 耗时={answer.latency_ms}ms "
              f"引用={len(answer.citations)} 拒答={answer.refused}")
        preview = answer.text.replace("\n", " ")[:120]
        print(f"[smoke]   A: {preview}…")
        if not answer.text.strip():
            failures += 1

    if failures:
        print(f"\n[smoke] ❌ {failures} 个问题返回空内容")
        return 1
    print("\n[smoke] ✅ 链路正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
