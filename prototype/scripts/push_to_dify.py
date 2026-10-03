"""把本地知识库批量推送到 Dify 数据集。

用法（在 prototype 目录下）：
    python scripts/push_to_dify.py --scene example_lab_safety --dry-run
    python scripts/push_to_dify.py --scene example_lab_safety

前置：.env 中配置 DIFY_API_BASE 与 DIFY_API_KEY（知识库 API Key，不是应用 Key）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.rag.chunker import list_documents  # noqa: E402
from app.scenes import load_scene  # noqa: E402


def create_dataset(api_base: str, api_key: str, name: str, description: str) -> str:
    response = httpx.post(
        f"{api_base}/datasets",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "name": name,
            "description": description,
            "indexing_technique": "high_quality",
            "permission": "only_me",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["id"]


def upload_document(api_base: str, api_key: str, dataset_id: str, path: Path, chunk_size: int, overlap: int) -> dict:
    process_rule = {
        "mode": "custom",
        "rules": {
            "pre_processing_rules": [
                {"id": "remove_extra_spaces", "enabled": True},
                {"id": "remove_urls_emails", "enabled": False},
            ],
            "segmentation": {
                "separator": "\n\n",
                "max_tokens": chunk_size,
                "chunk_overlap": overlap,
            },
        },
    }
    data = {
        "indexing_technique": "high_quality",
        "process_rule": process_rule,
        "doc_form": "text_model",
        "doc_language": "Chinese",
    }
    with path.open("rb") as handle:
        response = httpx.post(
            f"{api_base}/datasets/{dataset_id}/document/create-by-file",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"data": json.dumps(data, ensure_ascii=False)},
            files={"file": (path.name, handle, "application/octet-stream")},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="推送知识库到 Dify 数据集")
    parser.add_argument("--scene", default=None)
    parser.add_argument("--dataset-id", default=None, help="指定已有数据集；不填则新建")
    parser.add_argument("--name", default=None, help="新建数据集名称")
    parser.add_argument("--dry-run", action="store_true", help="只列出将要上传的文件")
    args = parser.parse_args()

    settings = get_settings()
    scene = load_scene(
        settings.scenes_dir, settings.knowledge_dir, args.scene or settings.scene_id
    )
    files = list_documents(scene.kb_dir)
    if not files:
        print(f"[push] 场景「{scene.name}」知识库为空：{scene.kb_dir}")
        return 1

    print(f"[push] 场景：{scene.name}")
    print(f"[push] 待上传 {len(files)} 个文件：")
    for path in files:
        print(f"    - {path.relative_to(scene.kb_dir)}")

    if args.dry_run:
        print("[push] dry-run，未实际上传")
        return 0

    if not settings.dify_api_key:
        print("[push] ❌ 未配置 DIFY_API_KEY，无法上传")
        return 1

    api_base = settings.dify_api_base.rstrip("/")
    dataset_id = args.dataset_id or settings.dify_dataset_id
    if not dataset_id:
        name = args.name or f"{scene.name}-知识库"
        print(f"[push] 新建数据集：{name}")
        dataset_id = create_dataset(api_base, settings.dify_api_key, name, scene.domain)
        print(f"[push] 数据集 ID：{dataset_id}")
        print("[push] ⚠️ 请把该 ID 写入 .env 的 DIFY_DATASET_ID")

    for path in files:
        try:
            result = upload_document(
                api_base,
                settings.dify_api_key,
                dataset_id,
                path,
                settings.chunk_size,
                settings.chunk_overlap,
            )
            document = result.get("document", {})
            print(f"    ✅ {path.name} → {document.get('id', 'unknown')}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ❌ {path.name} 上传失败：{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
