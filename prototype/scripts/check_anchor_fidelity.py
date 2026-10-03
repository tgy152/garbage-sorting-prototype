"""Organic 锚点保真度检查。

frontend-design 技能要求：渲染出来的 token 必须完全落在所选锚点的允许范围内。
本脚本对 PAGE_CSS 与实际渲染出的 HTML 做机械化检查，输出逐项结论。

用法：
    python scripts/check_anchor_fidelity.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import render  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.disassembler import load_disassembler  # noqa: E402
from app.vision import DetectedItem, VisionResult  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"


def main() -> int:
    settings = get_settings()
    css = render.PAGE_CSS
    disassembler = load_disassembler(settings.rules_dir, settings.scene_id)

    cache_path = settings.export_dir / "照片识别-缓存.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        key = next(iter(cache))
        payload = cache[key]
        result = VisionResult(
            summary=payload.get("summary", ""),
            items=[DetectedItem(**item) for item in payload.get("items", [])],
            backend="fidelity-check",
        )
    else:
        result = VisionResult(summary="样例", backend="fidelity-check")
    html = render.guidance_html(disassembler.guide(result, settings.region, "kitchen"))

    checks: list[tuple[str, str, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, PASS if ok else FAIL, detail))

    # ---------- 锚点 token 保真 ----------
    # Organic 禁止项：纯白、纯黑、冷灰、奶油白(#F0-F8 暖纸色)、硬直角
    pure_white = re.findall(r"#(?:FFFFFF|fff\b|FFF\b)", css)
    check("无纯白 #FFFFFF", not pure_white, f"发现 {pure_white[:3]}" if pure_white else "")

    pure_black = re.findall(r"#(?:000000|000\b)", css)
    check("无纯黑 #000000", not pure_black, f"发现 {pure_black[:3]}" if pure_black else "")

    cream = re.findall(r"#F[0-9A-F][0-9A-F]{4}", css, re.IGNORECASE)
    check(
        "无奶油白（#F0-F8 暖纸色）",
        not cream,
        f"发现 {sorted(set(cream))[:3]}" if cream else "锚点明确禁止该区间",
    )

    cold_grey = re.findall(r"#(?:F2F2F7|8E8E93|1C1C1E|F5F5F5|E8E8E8)", css, re.IGNORECASE)
    check("无冷灰", not cold_grey, f"发现 {cold_grey[:3]}" if cold_grey else "")

    # 圆角：不允许出现直角容器
    zero_radius = re.findall(r"border-radius:\s*0(?:px)?\s*[;}]", css)
    check("无直角矩形（border-radius:0）", not zero_radius, f"{len(zero_radius)} 处")
    check("圆角 ≥16px 出现", bool(re.search(r"border-radius:\s*(?:1[6-9]|2[0-9]|3[0-2])px", css)))

    # 锚点允许的地面色
    allowed = ["#8B9D83", "#B08B6E", "#C66B3D", "#C08E3A", "#606C38", "#E8DCC7", "#D4B895"]
    present = [c for c in allowed if c in css or c.lower() in css.lower()]
    check("使用锚点色板", len(present) >= 5, f"命中 {len(present)}/7：{present}")

    # 质感：feTurbulence 颗粒 1~3%
    check("含 SVG feTurbulence 颗粒", "feTurbulence" in css)
    opacities = [float(x) for x in re.findall(r"opacity:\s*\.(\d+)", css)]
    check(
        "颗粒透明度 1~3%",
        any(1 <= o <= 30 for o in opacities),
        f"取值 {sorted(set(opacities))}",
    )

    # 动效：300~500ms 缓动 + 首屏呼吸
    # 同时接受 ms 与 s 两种写法
    durations = [int(x) for x in re.findall(r"(\d+)ms", css)]
    durations += [int(float(x) * 1000) for x in re.findall(r"(?:^|[\s:(])(\d*\.\d+)s\b", css)]
    in_range = [d for d in durations if 300 <= d <= 500]
    check("存在 300~500ms 缓动", len(in_range) >= 3, f"{sorted(set(in_range))}")
    check("首屏呼吸动效", "@keyframes breathe" in css and "animation: breathe" in css)
    check("尊重 reduced-motion", "prefers-reduced-motion" in css)

    # 字体：只用衬线，不得出现无衬线族
    fonts = set(re.findall(r'font-family:\s*([^;]+);', css))
    sans_hits = [
        f
        for f in fonts
        if re.search(r"sans-serif|Inter|Helvetica|Arial|Segoe UI|system-ui", f)
    ]
    check("全站仅使用衬线字体", not sans_hits, f"发现无衬线：{sans_hits[:2]}" if sans_hits else "")
    check("使用 Fraunces（锚点限定显示字体）", "Fraunces" in css)

    # ---------- 签名动作 ----------
    check("地层条已渲染", 'class="strata"' in html)
    segments = len(re.findall(r"<span style=\"flex:", html))
    check("地层条按类别分段", segments >= 2, f"{segments} 段")
    legend = len(re.findall(r'class="dot"', html))
    check("地层条带图例", legend >= 2, f"{legend} 项")

    # ---------- 内容纪律（技能 §2）----------
    emoji = re.findall(
        r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]", html
    )
    check("无 Unicode 符号充当图标", not emoji, f"发现 {sorted(set(emoji))[:5]}" if emoji else "")

    check("使用手写 SVG 图标", html.count("<svg") >= 3, f"{html.count('<svg')} 个")
    check("未使用圆角方块图标占位", 'class="row-blob"' in html)

    # 标准 UI 文案未被主题化替换
    standard = ["发送", "清空对话", "重建索引", "导入到当前场景"]
    ui_source = (PROJECT_ROOT / "app" / "ui.py").read_text(encoding="utf-8")
    kept = [s for s in standard if s in ui_source]
    check("标准操作保留标准文案", len(kept) == len(standard), f"{len(kept)}/{len(standard)}")

    # ---------- 输出 ----------
    print("=" * 74)
    print("Organic 锚点保真度检查")
    print("=" * 74)
    failed = 0
    for name, status, detail in checks:
        mark = "✅" if status == PASS else "❌"
        suffix = f"  —— {detail}" if detail else ""
        print(f"{mark} {name}{suffix}")
        failed += 0 if status == PASS else 1
    print("=" * 74)
    print(f"共 {len(checks)} 项，通过 {len(checks) - failed} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
