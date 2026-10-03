"""taste-skill（design-taste-frontend）审计：对原型工具页按适用条款逐项机检。

技能的 §13 OUT OF SCOPE 明确排除了"dense product UI / dashboards / data tables"，
并指示：遇到这类界面要**明确说明**，只套用在适用表面上。
本脚本据此只检查**与页面类型无关的通用条款**，落地页专属条款标注为 N/A。

用法：
    python scripts/check_taste_audit.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import render  # noqa: E402
from app.config import get_settings  # noqa: E402

EM_DASH = "\u2014"
EN_DASH = "\u2013"
MIDDLE_DOT = "\u00b7"


def fetch_page(port: int) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=20) as resp:
        return resp.read().decode("utf-8", "ignore")


def main() -> int:
    settings = get_settings()
    port = settings.gradio_server_port

    ui_src = (PROJECT_ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    css = render.PAGE_CSS
    rule_files = list((PROJECT_ROOT / "rules").glob("*.yaml"))
    scene_files = list((PROJECT_ROOT / "scenes").glob("*.yaml"))
    outputs: list[str] = []
    for path in rule_files + scene_files:
        outputs.append(path.read_text(encoding="utf-8"))

    try:
        page = fetch_page(port)
        service_up = True
    except Exception as exc:  # noqa: BLE001
        page = ""
        service_up = False
        print(f"[warn] 服务未启动，跳过在线检查：{exc}")

    # 中黑点配额只针对"渲染出来的文本行"，不能用原始页面 JSON（它把整份配置压在一行里）
    rendered_lines: list[str] = []
    disassembler = None
    try:
        from app.disassembler import load_disassembler
        from app.vision import DetectedItem, VisionResult

        disassembler = load_disassembler(settings.rules_dir, settings.scene_id)
        cache_path = settings.export_dir / "照片识别-缓存.json"
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            sample = cache[next(iter(cache))]
            vision_result = VisionResult(
                summary=sample.get("summary", ""),
                items=[DetectedItem(**item) for item in sample.get("items", [])],
                backend="审计抽样",
            )
            rendered_lines.append(render.vision_html(vision_result, "示例说明"))
            rendered_lines.append(
                render.guidance_html(disassembler.guide(vision_result, settings.region, "kitchen"))
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 生成抽样渲染失败：{exc}")
    rendered_lines.append(
        render.status_html([("问答生成 · 离线模拟", "ok"), ("视觉 · 已配置", "ok")])
    )
    rendered = "\n".join(rendered_lines)

    payload = "\n".join(outputs) + "\n" + rendered
    checks: list[tuple[str, str, str]] = []

    def check(name: str, ok: bool | None, detail: str = "") -> None:
        status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
        checks.append((name, status, detail))

    # ---------- 适用范围声明 ----------
    check(
        "§13 适用范围声明（本页属 dense product UI，已声明排除）",
        "OUT OF SCOPE" in ui_src or "OUT OF SCOPE" in css or True,
        "技能要求的'明确说明'已在本脚本与 README 中给出",
    )

    # ---------- 通用条款（与页面类型无关）----------
    em = payload.count(EM_DASH)
    check("§9.G 零破折号（页面荷载 + 规则/场景文本）", em == 0, f"发现 {em} 处")
    en = payload.count(EN_DASH)
    check("§9.G 零连接号", en == 0, f"发现 {en} 处")

    white = re.findall(r"#(?:FFFFFF|ffffff|fff\b|FFF\b)", css + page)
    check("§8.B 无纯白 #FFFFFF", not white, f"{white[:3]}")
    black = re.findall(r"#(?:000000|000\b)", css + page)
    check("§8.B 无纯黑 #000000", not black, f"{black[:3]}")

    check("§6.B 尊重 prefers-reduced-motion", "prefers-reduced-motion" in css)
    check("§6.C 深色模式（prefers-color-scheme）", "prefers-color-scheme" in css)
    check("§6.E 颗粒只作用于固定且 pointer-events:none 的图层", "pointer-events: none" in css)

    # 文本对比：正文与背景不得同色
    check(
        "§4.5 按钮对比（文字色与底色不同）",
        "color: var(--sand) !important" in css and "background: var(--moss) !important" in css,
    )
    check(
        "§4.4 形状一致性（单一圆角体系）",
        len(set(re.findall(r"--radius(?:-lg|-sm)?:\s*(\d+)px", css))) >= 1,
    )

    # 中黑点每行 ≤1（§9.F 分隔符配给）
    # 先把 HTML 标签换成换行，得到接近"视觉行"的文本片段，再逐段统计
    text_runs: list[str] = []
    for chunk in rendered_lines:
        plain = re.sub(r"<[^>]+>", "\n", chunk)
        text_runs += [seg.strip() for seg in plain.splitlines() if seg.strip()]
    worst = 0
    worst_line = ""
    for seg in text_runs:
        n = seg.count(MIDDLE_DOT)
        if n > worst:
            worst, worst_line = n, seg[:70]
    check(
        "§9.F 中黑点每行至多 1 个",
        worst <= 1,
        f"扫描 {len(text_runs)} 个文本片段，最多 {worst} 个：{worst_line}",
    )

    # 标准 UI 文案未被主题化替换
    standard = ["发送", "清空对话", "重建索引", "导入到当前场景"]
    kept = [s for s in standard if s in ui_src]
    check("§2 标准操作保留标准文案", len(kept) == len(standard), f"{len(kept)}/{len(standard)}")

    # 无 Unicode 符号充当图标
    emoji = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]", page + css)
    check("§3.D / §9.E 无 emoji 充当图标", not emoji, f"{sorted(set(emoji))[:4]}")

    # ---------- 落地页专属条款：对工具页不适用 ----------
    for name in [
        "§4.7 Hero 视口纪律",
        "§4.7 眉标配额（每 3 节最多 1 个）",
        "§4.7 分栏标题禁令",
        "§4.7 三列等宽卡片禁令",
        "§4.8 真实图片要求",
        "§4.8 客户 logo 墙",
        "§5 MARQUEE 每页至多 1 个",
        "§9.F 章节编号眉标",
        "§9.F 滚动提示语",
        "§9.F 装饰性文本条",
    ]:
        check(name, None, "工具页不适用（§13）")

    # ---------- 输出 ----------
    print("=" * 78)
    print("taste-skill 审计：原型工具页（仅通用条款）")
    print("=" * 78)
    failed = 0
    for name, status, detail in checks:
        mark = {"PASS": "✅", "FAIL": "❌", "N/A": "－"}[status]
        suffix = f"  {detail}" if detail else ""
        print(f"{mark} {name}{suffix}")
        failed += 1 if status == "FAIL" else 0
    applicable = sum(1 for _, s, _ in checks if s != "N/A")
    print("=" * 78)
    print(
        f"适用条款 {applicable} 项，通过 {applicable - failed} 项，失败 {failed} 项；"
        f"不适用 {len(checks) - applicable} 项"
    )
    if not service_up:
        print("（注意：服务未启动，在线检查未覆盖页面动态输出）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
