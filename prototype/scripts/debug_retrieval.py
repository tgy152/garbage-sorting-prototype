"""调参用：打印每个问题的检索命中与分数，便于确定 TOP_K 与阈值。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.service import SceneService  # noqa: E402


def main() -> int:
    settings = get_settings()
    service = SceneService(settings, settings.scene_id)
    assert service.index is not None

    questions = service.scene.sample_questions
    for question in questions:
        print(f"\n=== {question}")
        hits = service.index.search(question, top_k=6, threshold=0.0)
        for hit in hits:
            preview = hit.chunk.text.replace("\n", " ")[:60]
            print(f"  {hit.score:.4f}  [{hit.chunk.source}] {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
