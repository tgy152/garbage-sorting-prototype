"""生成手机访问地址与二维码。

手机连不上通常有三个原因，本脚本会逐个检查并给出结论：
  1. 服务只绑定了 127.0.0.1（手机访问不到本机回环地址）；
  2. 手机与电脑不在同一个 WiFi；
  3. Windows 防火墙没有放行端口。

用法：
    python scripts/lan_access.py
    python scripts/lan_access.py --port 7860
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

VIRTUAL_HINTS = ("wsl", "hyper-v", "vethernet", "vmware", "virtualbox", "loopback")


def detect_lan_ip() -> tuple[str, str]:
    """返回 (本机局域网 IP, 网卡名)，优先选择无线/有线而非虚拟网卡。"""
    candidates: list[tuple[str, str]] = []
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | "
             "Select-Object -Property IPAddress,InterfaceAlias | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=25, check=False,
        ).stdout
        for line in output.splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) < 2:
                continue
            ip, alias = parts[0], parts[1]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            candidates.append((ip, alias))
    except Exception:  # noqa: BLE001
        pass

    if not candidates:
        # 退化方案：连一下外网，让系统选出出口网卡地址
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.connect(("8.8.8.8", 80))
                return probe.getsockname()[0], "默认出口网卡"
            except OSError:
                return "", ""

    for ip, alias in candidates:
        if not any(hint in alias.lower() for hint in VIRTUAL_HINTS):
            return ip, alias
    return candidates[0]


def make_qr(url: str, target: Path) -> bool:
    try:
        import qrcode
    except ImportError:
        print("（未安装 qrcode，跳过二维码生成：pip install qrcode）")
        return False
    image = qrcode.make(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="生成手机访问地址与二维码")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-qr", action="store_true")
    args = parser.parse_args()

    from app.config import get_settings

    settings = get_settings()
    port = args.port or settings.gradio_server_port

    ip, alias = detect_lan_ip()
    print(f"监听地址配置：{settings.gradio_server_name}")
    if settings.gradio_server_name in {"127.0.0.1", "localhost"}:
        print("  ⚠️ 只绑定了本机回环地址，手机无法访问。")
        print("     请把 .env 里的 GRADIO_SERVER_NAME 改成 0.0.0.0 后重启服务。")
    else:
        print("  ✅ 已绑定全部网卡，同一 WiFi 下的手机可以访问。")

    print(f"服务端口：{port}")
    if not ip:
        print("❌ 没有检测到局域网 IP，请确认已连接 WiFi。")
        return 1

    print(f"网卡：{alias}")
    url = f"http://{ip}:{port}"
    print()
    print(f"手机访问地址： {url}")
    print()
    print("手机打不开时依次检查：")
    print("  1. 手机与电脑连的是同一个 WiFi（不要一个连 5G、一个连 2.4G 的不同网段）")
    print("  2. Windows 防火墙是否放行（需要管理员权限执行一次）：")
    print(f'     netsh advfirewall firewall add rule name="Codex原型演示" '
          f"dir=in action=allow protocol=TCP localport={port}")
    print("  3. 电脑上服务是否在运行（本窗口不要关闭）")

    if not args.no_qr:
        target = settings.export_dir / "手机访问二维码.png"
        if make_qr(url, target):
            print()
            print(f"二维码已生成：{target}")
            print("用手机相机扫描该图片即可直接打开。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
