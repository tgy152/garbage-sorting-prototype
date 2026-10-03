"""生成 PWA 图标。

设计说明：
  图标是一枚字标（wordmark），取「分」字压在苔绿底上，暖沙色字形。
  这与原型界面的 Organic 配色一致（苔绿 #606C38 / 沙 #E8DCC7），
  也是 taste-skill 允许的"单一简单几何标记"，不是手绘装饰性插画。

  Android 的 maskable 图标会被裁成圆形，所以另出一版：
  底色铺满 + 字形缩到安全区内，避免圆形裁切把字削掉。

用法：
    python scripts/make_app_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT.parent / "pwa"

MOSS = (96, 108, 56)
SAND = (232, 220, 199)
FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:  # noqa: BLE001
                continue
    raise RuntimeError("找不到可用的中文字体，请检查 FONT_CANDIDATES")


def rounded_square(size: int, radius_ratio: float, background: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=int(size * radius_ratio),
        fill=background,
    )
    return img


def draw_glyph(img: Image.Image, glyph: str, size: int, occupy: float) -> None:
    """把字居中绘制，字形高度约占画布的 occupy 比例。"""
    target = int(size * occupy)
    font = load_font(target)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
    width, height = right - left, bottom - top
    draw.text(
        ((size - width) / 2 - left, (size - height) / 2 - top),
        glyph,
        font=font,
        fill=SAND,
    )


def main() -> int:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    glyph = "分"
    outputs: list[tuple[str, int, int]] = []

    # 普通图标：圆角方块 + 字形
    for size in (192, 512):
        img = rounded_square(size, 0.22, MOSS)
        draw_glyph(img, glyph, size, 0.58)
        path = APP_DIR / f"icon-{size}.png"
        img.convert("RGB").save(path, "PNG")
        outputs.append((path.name, size, path.stat().st_size))

    # maskable：底色铺满，字形收进安全区（圆形裁切后仍完整）
    img = Image.new("RGBA", (512, 512), MOSS + (255,))
    draw_glyph(img, glyph, 512, 0.40)
    path = APP_DIR / "icon-maskable-512.png"
    img.convert("RGB").save(path, "PNG")
    outputs.append((path.name, 512, path.stat().st_size))

    # iOS 主屏图标：不透明、无圆角（系统自己裁）
    img = Image.new("RGBA", (180, 180), MOSS + (255,))
    draw_glyph(img, glyph, 180, 0.56)
    path = APP_DIR / "apple-touch-icon.png"
    img.convert("RGB").save(path, "PNG")
    outputs.append((path.name, 180, path.stat().st_size))

    # 启动页背景色用得到的纯色块，供 manifest 与 meta 使用
    print(f"图标已生成到 {APP_DIR}")
    for name, size, size_bytes in outputs:
        print(f"  {name:26} {size}x{size}  {size_bytes / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
