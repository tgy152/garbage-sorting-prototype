"""验证 Gradio 公网分享链路是否可用（会生成一个临时公网地址，几秒后自动关闭）。

用途：确认当前网络能否访问 Gradio 的隧道服务。
如果这里失败，说明网络屏蔽了隧道，需要改用 Cloudflare Tunnel。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr  # noqa: E402


def main() -> int:
    with gr.Blocks(title="share test") as demo:
        gr.Markdown("# 公网分享测试\n\n如果你能在手机上看到这句话，说明链路可用。")

    print("[share-test] 正在建立公网隧道，通常需要 10~30 秒…")
    started = time.perf_counter()
    try:
        _, local_url, share_url = demo.queue().launch(
            server_name="127.0.0.1",
            server_port=7899,
            share=True,
            quiet=False,
            prevent_thread_lock=True,
            show_api=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[share-test] ❌ 建立失败：{exc}")
        return 1

    elapsed = time.perf_counter() - started
    print()
    print(f"[share-test] ✅ 本机地址：{local_url}")
    print(f"[share-test] ✅ 公网地址：{share_url}")
    print(f"[share-test] 耗时 {elapsed:.1f} 秒")
    print()
    print("[share-test] 5 秒后自动关闭隧道…")
    time.sleep(5)
    demo.close()
    print("[share-test] 已关闭")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
