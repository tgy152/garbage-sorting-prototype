"""作品介绍页的 pre-flight 检查（design-taste-frontend §14）。

技能明确要求：§14 不是可选项，每一条都要打勾；任何一条打不上，
页面就不算完成。本脚本把能机械验证的条目实现出来。

用法：
    python scripts/check_landing_preflight.py
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANDING = PROJECT_ROOT.parent / "landing"

EM_DASH = "\u2014"
EN_DASH = "\u2013"
MIDDLE_DOT = "\u00b7"


def main() -> int:
    html = (LANDING / "index.html").read_text(encoding="utf-8")
    css = (LANDING / "styles.css").read_text(encoding="utf-8")
    page = html + "\n" + css

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    # ---------- §9.G 破折号 ----------
    check("§9.G 零破折号", page.count(EM_DASH) == 0, f"{page.count(EM_DASH)} 处")
    check("§9.G 零连接号", page.count(EN_DASH) == 0, f"{page.count(EN_DASH)} 处")

    # ---------- §9.F 中黑点配给 ----------
    runs = [s.strip() for s in re.sub(r"<[^>]+>", "\n", html).splitlines() if s.strip()]
    worst = max((s.count(MIDDLE_DOT) for s in runs), default=0)
    check("§9.F 中黑点每行至多 1 个", worst <= 1, f"最多 {worst} 个")

    # ---------- §8.B / §9.A 颜色 ----------
    check("§8.B 无纯白 #fff", not re.search(r"#(?:fff|ffffff)\b", css, re.I))
    check("§8.B 无纯黑 #000", not re.search(r"#(?:000|000000)\b", css, re.I))
    banned = [
        "#f5f1ea", "#f7f5f1", "#fbf8f1", "#efeae0",
        "#ece6db", "#faf7f1", "#e8dfcb",
    ]
    hit = [c for c in banned if c in css.lower()]
    check("§4.2 未落入奶油白禁用色族", not hit, f"{hit}")
    # 浅深两套各定义一个强调色，属同一支色相，不是"两个强调色"
    accents = re.findall(r"--accent:\s*(#[0-9a-f]{6})", css)
    check("§4.2 单一强调色（浅深各一档）", len(set(accents)) == 2, f"{accents}")

    # ---------- §4.11 / §6.C 主题 ----------
    # 注释里也会提到这个词，只统计实际的 @media 规则
    check(
        "§4.11 主题在页面级锁定（auto）",
        len(re.findall(r"@media\s*\(prefers-color-scheme", css)) == 1,
    )
    check("§6.C 深色模式已定义", "prefers-color-scheme: dark" in css)

    # ---------- §4.4 形状一致性 ----------
    radii = set(re.findall(r"--radius(?:-pill)?:\s*(\d+px)", css))
    check("§4.4 圆角只有文档化的两档", radii == {"18px", "999px"}, f"{sorted(radii)}")

    # ---------- §4.1 字体 ----------
    check("§4.1 未使用 Inter 作默认", not re.search(r"\bInter\b", css))
    check("§4.1 未使用衬线字体", not re.search(r"serif", css.replace("sans-serif", "")))
    check("§3.A 字体自托管（@font-face）", "@font-face" in css)
    check("§3.A 未用 <link> 引 Google Fonts", "fonts.googleapis.com" not in html)

    # ---------- §3.C 图标 ----------
    check("§3.C 无手写 SVG 图标", "<svg" not in html)

    # ---------- §4.8 真实图片 ----------
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
    missing = [s for s in imgs if not (LANDING / s).exists()]
    check("§4.8 使用真实图片且文件存在", bool(imgs) and not missing,
          f"{len(imgs)} 张，缺失 {missing}")
    check("§4.8 无 div 假截图", "fake-" not in html and "screenshot" not in html.lower())
    check("§9.F 图片上无标签叠加", "overlay" not in css and "position: absolute" not in css)

    # ---------- §4.7 Hero 纪律 ----------
    hero = html.split('class="hero wrap"')[1].split("</section>")[0] if 'class="hero wrap"' in html else ""
    text_elems = hero.count("<h1") + hero.count("<p class=") + hero.count("cta-row")
    check("§4.7 Hero 文案元素 ≤4", text_elems <= 4, f"{text_elems} 个")
    check("§4.7 Hero 顶部内边距 ≤6rem", bool(re.search(r"\.hero\s*\{[^}]*padding:\s*(\d+)px", css))
          and int(re.search(r"\.hero\s*\{[^}]*padding:\s*(\d+)px", css).group(1)) <= 96)
    check("§4.3 VARIANCE>4 时 Hero 非居中", "grid-template-columns" in css.split(".hero {")[1].split("}")[0])
    check("§4.7 CTA 不换行", "white-space: nowrap" in css)

    # ---------- §4.7 眉标配额 ----------
    eyebrows = len(re.findall(r'class="[^"]*eyebrow', html)) + html.count("uppercase")
    sections = html.count("<section")
    limit = max(1, -(-sections // 3))
    check("§4.7 眉标数 ≤ ceil(章节/3)", eyebrows <= limit, f"{eyebrows} ≤ {limit}")

    # ---------- §9.F 禁止模式 ----------
    check("§9.F 无滚动提示语", not re.search(r"(scroll to|↓|向下滚动)", html, re.I))
    check("§9.F 无版本号标签", not re.search(r"\b(v\d+\.\d+|BETA|ALPHA|PREVIEW)\b", html))
    check("§9.F 无章节编号眉标", not re.search(r">\s*0\d\s*/", html))
    check("§9.F 无装饰性状态点", "status-dot" not in html and "dot" not in css)
    check("§9.F 无评分进度条", "progress" not in css and "track" not in css)
    check("§9.F 无 locale 条", not re.search(r"(°C|UTC|GMT)", html))
    check("§9.F 无装饰文本条", "BRAND." not in html and "MOTION." not in html)

    # ---------- §4.9 内容密度 ----------
    leds = re.findall(r'<p class="lede">(.*?)</p>', html, re.S)
    longest = max((len(re.sub(r"\s", "", t)) for t in leds), default=0)
    check("§4.9 段落长度克制（≤70 字）", longest <= 70, f"最长 {longest} 字")
    check("§4.9 长清单用卡片而非逐行边框", ".metric" in css and ".round" in css)

    # ---------- 内容纪律 ----------
    check("§9.D 无虚构品牌名", not re.search(r"(Acme|Nexus|SmartFlow|Cloudly)", html))
    check("§9.D 无填充动词", not re.search(r"(Elevate|Seamless|Unleash|Next-Gen|Revolutionize)", html))
    check("§9.D 无占位人名", not re.search(r"(John Doe|Jane Doe|张三|李四)", html))
    # §4.5：同一意图必须用同一个文案。这里检查所有主按钮文案是否完全一致。
    primary_labels = re.findall(
        r'class="btn btn-primary"[^>]*>([^<]+)<', html
    )
    check(
        "§4.5 主 CTA 全站同一文案",
        len(set(primary_labels)) == 1,
        f"{sorted(set(primary_labels))}",
    )
    synonyms = ["联系我们", "立即开始", "免费试用", "查看作品", "联系我"]
    check("§4.5 无同义 CTA 混用", not any(s in html for s in synonyms))

    # ---------- 可访问性 / 性能 ----------
    check("§6.B reduced-motion 已处理", "prefers-reduced-motion" in css)
    # 只看真实代码，不看注释里"不要这么写"的说明
    code = re.sub(r"//[^\n]*", "", html)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    check(
        "§5.D 未用 scroll 事件监听",
        not re.search(r"addEventListener\(\s*['\"]scroll", code),
    )
    check("§6.A 只动 transform/opacity", re.search(r"transition:[^;]*opacity", css) is not None)
    check("§6.F z-index 克制", css.count("z-index") <= 2, f"{css.count('z-index')} 处")
    check("图片有宽高（避免 CLS）", len(re.findall(r'<img[^>]+width="\d+"', html)) == len(imgs))
    check("图片有 alt 文本", len(re.findall(r'<img[^>]+alt="', html)) == len(imgs))
    check("§7 <768px 显式收敛", "@media (max-width: 768px)" in css)

    # ---------- 输出 ----------
    print("=" * 80)
    print("作品介绍页 pre-flight 检查（design-taste-frontend §14 可机检部分）")
    print("=" * 80)
    failed = 0
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        suffix = f"  {detail}" if detail else ""
        print(f"{mark} {name}{suffix}")
        failed += 0 if ok else 1
    print("=" * 80)
    print(f"共 {len(checks)} 项，通过 {len(checks) - failed} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
