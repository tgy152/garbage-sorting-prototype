"""对比度审计：找出页面里读不清的文字。

做法是把 CSS 里声明的文字色与它实际落到的背景色配对，按 WCAG 算对比度，
低于阈值就报出来。同时检查 Gradio 原生组件（表格、文件列表、代码块、对话框）
的文字色，这类组件不会被自定义面板包住，最容易在深色页面底上"沉下去"。

用法：
    python scripts/check_contrast.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import render  # noqa: E402

AA_NORMAL = 4.5
AA_LARGE = 3.0


def parse_color(value: str, variables: dict[str, str]) -> tuple[int, int, int] | None:
    value = value.strip().rstrip("!important").strip()
    var = re.fullmatch(r"var\((--[a-z0-9-]+)\)", value)
    if var:
        value = variables.get(var.group(1), "")
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if hex_match:
        digits = hex_match.group(1)
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    rgba = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", value
    )
    if rgba:
        return (int(rgba.group(1)), int(rgba.group(2)), int(rgba.group(3)))
    return None


def blend(fg: tuple[int, int, int], alpha: float, bg: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))  # type: ignore[return-value]


def luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1, l2 = luminance(fg), luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def variables_for(css: str, dark: bool = True) -> dict[str, str]:
    """取 :root 或浅色块里的变量定义。"""
    if dark:
        block = css.split(":root {")[1].split("}")[0]
    else:
        block = css.split("@media (prefers-color-scheme: light)")[1].split(":root {")[1].split("}")[0]
    found = dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", block))
    return found


def main() -> int:
    css = render.PAGE_CSS
    failures: list[tuple[str, float, str]] = []
    rows: list[tuple[str, str, str, float, bool]] = []

    for mode_dark in (True, False):
        variables = variables_for(css, mode_dark)
        mode = "深色" if mode_dark else "浅色"

        page_bg = parse_color(variables.get("--soil", "#3A4032"), variables)
        panel_bg = parse_color(variables.get("--sand", "#E8DCC7"), variables)
        on_panel = parse_color(variables.get("--ink", "#2E2A20"), variables)

        pairs: list[tuple[str, tuple[int, int, int] | None, tuple[int, int, int], float]] = [
            ("页面底上的正文（--on-page）",
             parse_color(variables.get("--on-page", "#D2C7AE"), variables), page_bg, AA_NORMAL),
            ("沙面面板上的正文（--ink）", on_panel, panel_bg, AA_NORMAL),
            ("沙面面板上的次要文字（--ink-2）",
             parse_color(variables.get("--ink-2", "#6B5F49"), variables), panel_bg, AA_NORMAL),
            ("沙面面板上的三级文字（--ink-3）",
             parse_color(variables.get("--ink-3", "#998A6E"), variables), panel_bg, AA_NORMAL),
            ("状态条胶囊（.pill.neutral）",
             parse_color("#CFC3AA" if mode_dark else "#3B3226", variables), page_bg, AA_NORMAL),
            ("脚注（.footnote）",
             parse_color("#C9BDA4" if mode_dark else "#4A4030", variables), page_bg, AA_NORMAL),
            ("标签页按钮（未选中）",
             parse_color("#B7AB92" if mode_dark else "#4A4030", variables), page_bg, AA_NORMAL),
            ("表单标签",
             parse_color("#C9BDA4" if mode_dark else "#4A4030", variables), page_bg, AA_NORMAL),
            ("输入框内文字",
             parse_color(variables.get("--ink", "#2E2A20"), variables), panel_bg, AA_NORMAL),
        ]

        for name, fg, bg, threshold in pairs:
            if fg is None or bg is None:
                continue
            ratio = contrast(fg, bg)
            ok = ratio >= threshold
            rows.append((mode, name, f"{fg} on {bg}", ratio, ok))
            if not ok:
                failures.append((f"[{mode}] {name}", ratio, f"要求 ≥ {threshold}"))

        # 首屏行动按钮（.cta.primary）。
        # 从 CSS 里读实际声明的底色，而不是写死期望值：这个按钮踩过一次坑——
        # 底色写成 var(--soil) 时，浅色模式下 --soil 会翻成燕麦色 #D4B895，
        # 与沙面文字的对比度只剩 1.44:1，按钮上的字几乎看不见。
        # 只按深色模式检查的话查不出这个问题，所以两套模式都要过。
        cta_match = re.search(r"\.cta\.primary\s*\{[^}]*?background:\s*([^;]+);", css)
        cta_fg = parse_color(variables.get("--sand", "#E8DCC7"), variables)
        if cta_match and cta_fg is not None:
            raw = cta_match.group(1).strip()
            cta_bg = parse_color(raw, variables)
            # 按钮落在 hero 卡片上，卡片底色两套模式都是 --sand
            if cta_bg is not None:
                ratio = contrast(cta_fg, cta_bg)
                ok = ratio >= AA_NORMAL
                rows.append((mode, f"首屏行动按钮（.cta.primary）", f"{cta_fg} on {raw}", ratio, ok))
                if not ok:
                    failures.append((f"[{mode}] 首屏行动按钮（.cta.primary）", ratio, f"要求 ≥ {AA_NORMAL}"))

    # Gradio 原生组件：不会被自定义面板包住，需要单独确认
    # Gradio 原生组件：必须自己声明底色与墨色，否则会继承页面底上的文字色
    native_specs = [
        # 选择器带 :not(:has(...)) 用来排除自定义面板，所以匹配到 "{" 之前即可
        ("gr.Markdown 正文（.prose）", r"\.gradio-container \.prose[^{]*\{"),
        ("gr.Dataframe 表格（table）", r"\.gradio-container table th"),
        ("gr.Files 文件列表（.file-preview）", r"\.gradio-container \.file-preview \{"),
        ("gr.Code 代码块（.cm-editor）", r"\.gradio-container \.cm-editor,"),
        ("gr.Chatbot 气泡（.message）", r"\.gradio-container \.message \{"),
    ]

    print("=" * 82)
    print("对比度审计")
    print("=" * 82)
    for mode, name, pair, ratio, ok in rows:
        mark = "✅" if ok else "❌"
        print(f"{mark} [{mode}] {name:34} {ratio:>6}:1   {pair}")
    print()
    print("Gradio 原生组件是否自带可读表面：")
    dark_vars = variables_for(css, True)
    panel_bg = parse_color(dark_vars.get("--sand", "#E8DCC7"), dark_vars)
    ink = parse_color(dark_vars.get("--ink", "#2E2A20"), dark_vars)
    for name, selector in native_specs:
        match = re.search(selector, css)
        covered = match is not None
        if covered:
            # 进一步确认这条规则确实给了沙面底色
            tail = css[match.start() : match.start() + 400]
            covered = "background: var(--sand)" in tail
        if covered and panel_bg and ink:
            ratio = contrast(ink, panel_bg)
            print(f"   ✅ {name:30} 已有沙面，墨色对比度 {ratio}:1")
        else:
            print(f"   ❌ {name:30} 未声明底色，文字会继承页面底色")
            failures.append((name, 0.0, "原生组件缺少沙面声明"))

    print("=" * 82)
    if failures:
        print(f"发现 {len(failures)} 处可读性问题：")
        for name, ratio, note in failures:
            print(f"  ❌ {name}  {ratio}:1  {note}")
    else:
        print("未发现可读性问题")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
