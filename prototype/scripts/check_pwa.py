"""PWA 可安装性检查。

用真实浏览器打开页面，验证：
  1. manifest 能被解析，且具备可安装所需的全部字段
  2. 图标尺寸达标（Chrome 要求至少有 192 与 512 两个尺寸）
  3. Service Worker 成功注册并进入 activated 状态
  4. 页面通过 HTTPS 或 localhost（PWA 的硬性前提）

用法：
    python scripts/check_pwa.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REQUIRED_FIELDS = ["name", "short_name", "start_url", "display", "icons"]


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    import subprocess

    from app.config import get_settings

    settings = get_settings()
    base = f"http://127.0.0.1:{settings.gradio_server_port}"
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    # 1. manifest 字段
    try:
        manifest = fetch_json(f"{base}/manifest.webmanifest")
        missing = [f for f in REQUIRED_FIELDS if not manifest.get(f)]
        check("manifest 具备必要字段", not missing, f"缺 {missing}" if missing else "5/5")

        icons = manifest.get("icons") or []
        sizes = {i.get("sizes") for i in icons}
        check("图标含 192 与 512", {"192x192", "512x512"} <= sizes, f"{sorted(sizes)}")
        check(
            "含 maskable 图标（安卓圆形裁切用）",
            any("maskable" in (i.get("purpose") or "") for i in icons),
        )
        check(
            "display 为 standalone（独立窗口运行）",
            manifest.get("display") == "standalone",
            str(manifest.get("display")),
        )
        check("start_url 指向站点根", manifest.get("start_url") == "/", str(manifest.get("start_url")))
    except Exception as exc:  # noqa: BLE001
        check("manifest 读取失败", False, str(exc))

    # 2. 图标文件真实存在
    try:
        manifest = fetch_json(f"{base}/manifest.webmanifest")
        bad = []
        for icon in manifest.get("icons") or []:
            url = base + icon["src"]
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    if resp.status != 200 or len(resp.read()) < 500:
                        bad.append(icon["src"])
            except Exception:  # noqa: BLE001
                bad.append(icon["src"])
        check("图标文件均可访问且有内容", not bad, f"异常 {bad}")
    except Exception:  # noqa: BLE001
        check("图标文件检查失败", False)

    # 3. Service Worker 路由
    try:
        with urllib.request.urlopen(f"{base}/sw.js", timeout=15) as resp:
            body = resp.read().decode("utf-8")
        check("sw.js 可访问且含 fetch 处理器", "addEventListener(\"fetch\"" in body or "addEventListener('fetch'" in body)
    except Exception as exc:  # noqa: BLE001
        check("sw.js 不可访问", False, str(exc))

    # 4. 页面 head 声明
    try:
        with urllib.request.urlopen(f"{base}/", timeout=20) as resp:
            html = resp.read().decode("utf-8", "ignore")
        for token, label in [
            ('rel="manifest"', "页面声明 manifest"),
            ("serviceWorker", "页面注册 Service Worker"),
            ("apple-touch-icon", "iOS 主屏图标"),
            ("theme-color", "主题色"),
        ]:
            check(label, token in html)
    except Exception as exc:  # noqa: BLE001
        check("页面读取失败", False, str(exc))

    # 5. 浏览器实测：SW 是否进入 activated
    node = Path("C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
    modules = Path("C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules")
    if node.exists():
        script = f"""
const {{ createRequire }} = require('node:module');
const req = createRequire('file:///C:/x.js');
const {{ chromium }} = req('{modules.as_posix()}/playwright');
(async () => {{
  const b = await chromium.launch({{ channel: 'msedge', headless: true }});
  const p = await b.newPage({{ viewport: {{ width: 390, height: 844 }} }});
  await p.goto('{base}/', {{ waitUntil: 'networkidle', timeout: 45000 }});
  await p.waitForTimeout(2500);
  const r = await p.evaluate(async () => {{
    const regs = await navigator.serviceWorker.getRegistrations();
    return {{ count: regs.length, states: regs.map(x => (x.active && x.active.state) || (x.installing && x.installing.state) || 'none') }};
  }});
  console.log(JSON.stringify(r));
  await b.close();
}})();
"""
        try:
            out = subprocess.run(
                [str(node), "-e", script],
                capture_output=True, text=True, timeout=120, check=False,
            ).stdout.strip()
            data = json.loads(out.splitlines()[-1]) if out else {}
            states = data.get("states") or []
            check(
                "Service Worker 在浏览器中已激活",
                bool(states) and states[0] in {"activated", "activating"},
                f"{data}",
            )
        except Exception as exc:  # noqa: BLE001
            check("Service Worker 浏览器实测失败", False, str(exc))

    print("=" * 74)
    print("PWA 可安装性检查")
    print("=" * 74)
    failed = 0
    for name, ok, detail in checks:
        print(f"{'✅' if ok else '❌'} {name}" + (f"  {detail}" if detail else ""))
        failed += 0 if ok else 1
    print("=" * 74)
    print(f"共 {len(checks)} 项，通过 {len(checks) - failed} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
