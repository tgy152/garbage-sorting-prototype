"""一键启动：本机服务 + Cloudflare 公网隧道。

效果：无论手机连的是 WiFi 还是流量，只要打开生成的公网地址就能访问。

做法：
  1. 检查本机服务是否在跑，没跑就拉起来；
  2. 检查 cloudflared 是否存在，没有就自动下载；
  3. 建立快速隧道（trycloudflare.com），从日志里提取公网地址；
  4. 打印地址并生成二维码，按 Ctrl+C 结束。

用法（在 prototype 目录下执行）：
    python scripts/start_public.py
    python scripts/start_public.py --port 7860

注意：
  · 快速隧道的地址每次启动都会变；
  · 公网地址任何人拿到都能访问，务必在 .env 里设置 GRADIO_AUTH_USER / GRADIO_AUTH_PASSWORD。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def local_service_ready(port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def ensure_cloudflared(tools_dir: Path) -> Path:
    binary = tools_dir / "cloudflared.exe"
    if binary.exists():
        return binary
    print("[public] 未找到 cloudflared，正在下载（约 53 MB）…")
    tools_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(CLOUDFLARED_URL, binary)
    print(f"[public] 下载完成：{binary}")
    return binary


def make_qr(url: str, target: Path) -> bool:
    try:
        import qrcode
    except ImportError:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(url).save(target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="启动本机服务 + 公网隧道")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-app", action="store_true", help="只开隧道，不管本机服务")
    args = parser.parse_args()

    from app.config import get_settings

    settings = get_settings()
    port = args.port or settings.gradio_server_port
    # 每次运行用独立日志文件，避免上一次的隧道进程还占着日志导致启动失败
    log_path = settings.export_dir.parent / f"cloudflared-{os.getpid()}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    app_process: subprocess.Popen | None = None
    tunnel_process: subprocess.Popen | None = None

    try:
        # 1) 本机服务
        if args.no_app:
            if not local_service_ready(port):
                print(f"❌ 本机 {port} 端口没有服务在跑")
                return 1
            print(f"[public] 复用已有服务：http://127.0.0.1:{port}")
        elif local_service_ready(port):
            print(f"[public] 检测到服务已在运行：http://127.0.0.1:{port}")
        else:
            print("[public] 启动本机服务…")
            app_process = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "GRADIO_INBROWSER": "false"},
            )
            for _ in range(60):
                if local_service_ready(port):
                    break
                time.sleep(1)
            if not local_service_ready(port):
                print("❌ 本机服务启动超时")
                return 1
            print(f"[public] 服务已就绪：http://127.0.0.1:{port}")

        # 2) 公网隧道
        binary = ensure_cloudflared(PROJECT_ROOT / "tools")
        try:
            if log_path.exists():
                log_path.unlink()
        except OSError:
            pass  # 罕见情况下日志被占用，继续使用即可
        print("[public] 建立公网隧道…")
        tunnel_process = subprocess.Popen(
            [
                str(binary),
                "tunnel",
                "--url", f"http://127.0.0.1:{port}",
                "--no-autoupdate",
                "--logfile", str(log_path),
                "--loglevel", "info",
            ],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        public_url = ""
        for _ in range(60):
            time.sleep(1)
            if log_path.exists():
                found = URL_PATTERN.findall(log_path.read_text(encoding="utf-8", errors="ignore"))
                if found:
                    public_url = found[0]
                    break
            if tunnel_process.poll() is not None:
                print("❌ 隧道进程提前退出，请检查网络是否屏蔽了 cloudflare")
                return 1

        if not public_url:
            print("❌ 未能获取公网地址（超时 60 秒）")
            return 1

        # 3) 输出
        print()
        print("=" * 62)
        print("  公网访问已开启 —— 手机用 WiFi 或流量都能打开")
        print("=" * 62)
        print(f"  公网地址： {public_url}")
        print(f"  本机地址： http://127.0.0.1:{port}")
        if settings.auth_enabled:
            print(f"  访问账号： {settings.gradio_auth_user}（密码见 .env）")
        else:
            print("  ⚠️ 未设置访问密码：拿到链接的人都能用你的模型额度")
            print("     请在 .env 设置 GRADIO_AUTH_USER / GRADIO_AUTH_PASSWORD 后重启")
        print("=" * 62)
        print()

        # 作品介绍页与原型共用一条隧道，因此只需在自己的地址后加 /landing/
        targets = [("原型", f"{public_url}/", "公网访问二维码.png")]
        landing_dir = PROJECT_ROOT.parent / "landing"
        if landing_dir.exists():
            targets.append(("作品页", f"{public_url}/landing/", "作品页二维码.png"))
        for label, url, filename in targets:
            qr_path = settings.export_dir / filename
            if make_qr(url, qr_path):
                print(f"  {label}二维码：{qr_path}")
        print()
        print(f"  作品介绍页： {public_url}/landing/")
        print()
        print("按 Ctrl+C 结束（隧道会同时关闭）。")

        while True:
            time.sleep(2)
            if tunnel_process.poll() is not None:
                print("[public] 隧道已断开")
                break
    except KeyboardInterrupt:
        print("\n[public] 正在关闭…")
    finally:
        for process in (tunnel_process, app_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        print("[public] 已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
