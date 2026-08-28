"""Generate placeholder Rich Menu images (2500x1686) from a rich-menu YAML.

`scripts/sync_line_rich_menu.py --apply` needs an uploaded image alongside
each menu's tap-region config — LINE renders whatever image you give it and
overlays invisible tap regions on top; the YAML's `label` values are only
used for `displayText`, never drawn on the menu itself. This script draws one
evenly divided panel per action (matching `sync_line_rich_menu.layout_areas`'s
geometry, so the visible blocks line up with the real tap regions), styled as
a soft pastel gradient card with a floating icon badge (drop shadow, color
emoji), a paw-print/star decoration, and a wavy accent stripe — the closest
Pillow (flat 2D drawing) can get to a polished "3D sticker" look without a
real illustration/AI-art tool. One PNG is written per entry in the YAML's
`menus:` list, named `line-rich-menu-<key>.png`.

Usage:
  uv run python -m scripts.generate_rich_menu_image \
      --config infra/local/line-rich-menu.yaml \
      --out-dir infra/local
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scripts.sync_line_rich_menu import layout_areas

WIDTH = 2500
HEIGHT = 1686
BG_COLOR = "#FFF8EF"
FRAME_COLOR = "#4A3F38"
TEXT_COLOR = "#4A3F38"
STAR_COLOR = "#FFD966"
FRAME_WIDTH = 20
FRAME_INSET = 16
FRAME_RADIUS = 70
DIVIDER_WIDTH = 8

# (gradient top, gradient bottom, icon-badge fill) per cell, cycled by index.
ACCENT_PALETTE = [
    ("#FCE2D6", "#FFF8EF", "#E2836E"),
    ("#E3EDD3", "#FFF8EF", "#84A75C"),
    ("#E9DDF0", "#FFF8EF", "#A47EC6"),
    ("#DCE9F3", "#FFF8EF", "#6C9BC3"),
]

_LABEL_EMOJI = {
    "開始照護回報": "\U0001f4f7",
    "掃描 QR Code": "\U0001f50d",
    "今日照護毛孩": "\U0001f415",
    "繼續未完成回報": "\U0001f4dd",
    "聯絡工作人員": "\U0001f3a7",
    "開啟管理入口": "\U0001f5c2",
    "領養媒合": "\U0001f49b",
    "領養後追蹤": "\U0001f4cb",
    "毛孩日記": "\U0001f4d3",
    "北區": "\U0001f4cd",
    "中區": "\U0001f4cd",
    "南區": "\U0001f4cd",
    "東區": "\U0001f4cd",
    "我心有所屬": "\U0001f49b",
    "請推薦給我": "\U0001f31f",
}
_DEFAULT_EMOJI = "\U0001f43e"
_REGION_LETTER = {"北區": "N", "中區": "C", "南區": "S", "東區": "E"}


def _cjk_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/mingliu.ttc",
        # Same fonts, reached via WSL's mount of the Windows C: drive — this
        # script is often invoked from inside the project's WSL venv.
        "/mnt/c/Windows/Fonts/msjh.ttc",
        "/mnt/c/Windows/Fonts/mingliu.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    candidates = [
        "C:/Windows/Fonts/seguiemj.ttf",
        "/mnt/c/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return None


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    width, height = size
    top_rgb, bottom_rgb = _hex_rgb(top), _hex_rgb(bottom)
    column = Image.new("RGB", (1, max(height, 1)))
    for y in range(max(height, 1)):
        t = y / max(height - 1, 1)
        column.putpixel(
            (0, y), tuple(int(top_rgb[c] + (bottom_rgb[c] - top_rgb[c]) * t) for c in range(3))
        )
    return column.resize((max(width, 1), max(height, 1)))


def _paw_print(size: int, color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx, cy = size / 2, size * 0.62
    pad_w, pad_h = size * 0.42, size * 0.34
    draw.ellipse([cx - pad_w / 2, cy - pad_h / 2, cx + pad_w / 2, cy + pad_h / 2], fill=color)
    toe_r = size * 0.13
    for ox, oy in [(-0.30, -0.30), (-0.08, -0.44), (0.14, -0.42), (0.32, -0.24)]:
        tx, ty = cx + ox * size, cy + oy * size
        draw.ellipse([tx - toe_r, ty - toe_r, tx + toe_r, ty + toe_r], fill=color)
    return image


def _star(size: int, color: str) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cx, cy, r_out, r_in = size / 2, size / 2, size * 0.48, size * 0.20
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_in
        points.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    draw.polygon(points, fill=color)
    return image


def _wrap_label(label: str, max_chars: int = 4) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in label:
        if len(current) >= max_chars:
            lines.append(current)
            current = ""
        current += ch
    if current:
        lines.append(current)
    return lines


def build_image(actions: list[dict]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    areas = layout_areas(actions)

    cells = []
    for index, area in enumerate(areas):
        bounds = area["bounds"]
        x0, y0 = bounds["x"], bounds["y"]
        x1, y1 = x0 + bounds["width"], y0 + bounds["height"]
        top_c, bottom_c, badge_c = ACCENT_PALETTE[index % len(ACCENT_PALETTE)]
        image.paste(_vertical_gradient((x1 - x0, y1 - y0), top_c, bottom_c), (x0, y0))
        cw, ch = x1 - x0, y1 - y0
        badge_size = min(cw, ch) * 0.34
        bx, by = x0 + cw / 2, y0 + ch * 0.34
        cells.append(
            {
                "bounds": (x0, y0, x1, y1),
                "badge_center": (bx, by),
                "badge_size": badge_size,
                "badge_color": _hex_rgb(badge_c),
                "badge_hex": badge_c,
                "label": str(actions[index].get("label", "")),
            }
        )

    # Wavy accent stripe along the bottom of each cell, on its own
    # transparent layer so the fill alpha actually blends onto the gradient.
    stripes = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    stripe_draw = ImageDraw.Draw(stripes)
    for index, cell in enumerate(cells):
        x0, y0, x1, y1 = cell["bounds"]
        stripe_h = (y1 - y0) * 0.10
        amplitude = stripe_h * 0.35
        base_y = y1 - stripe_h
        points = [(x0, y1)]
        steps = 24
        for step in range(steps + 1):
            t = step / steps
            x = x0 + t * (x1 - x0)
            y = base_y + amplitude * math.sin(t * math.pi * 2 + index)
            points.append((x, y))
        points.append((x1, y1))
        stripe_draw.polygon(points, fill=(*cell["badge_color"], 70))
    image = Image.alpha_composite(image.convert("RGBA"), stripes)

    # Icon badge drop shadows, blurred once on their own layer.
    shadows = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadows)
    for cell in cells:
        bx, by = cell["badge_center"]
        half = cell["badge_size"] / 2
        radius = cell["badge_size"] * 0.26
        shadow_draw.rounded_rectangle(
            [bx - half + 14, by - half + 22, bx + half + 14, by + half + 22],
            radius=radius,
            fill=(30, 20, 15, 110),
        )
    shadows = shadows.filter(ImageFilter.GaussianBlur(20))
    image = Image.alpha_composite(image, shadows).convert("RGB")

    draw = ImageDraw.Draw(image)
    label_font = _cjk_font(60)
    emoji_font = _emoji_font(130)

    for cell in cells:
        bx, by = cell["badge_center"]
        badge_size = cell["badge_size"]
        half = badge_size / 2
        radius = badge_size * 0.26
        draw.rounded_rectangle(
            [bx - half, by - half, bx + half, by + half], radius=radius, fill=cell["badge_hex"]
        )

        emoji = _LABEL_EMOJI.get(cell["label"], _DEFAULT_EMOJI)
        if emoji_font is not None:
            draw.text((bx, by), emoji, font=emoji_font, anchor="mm", embedded_color=True)
        else:
            draw.ellipse(
                [bx - half * 0.6, by - half * 0.6, bx + half * 0.6, by + half * 0.6],
                outline="#FFFFFF",
                width=6,
            )

        letter = _REGION_LETTER.get(cell["label"])
        if letter:
            lr = badge_size * 0.20
            lx, ly = bx - badge_size * 0.38, by - badge_size * 0.38
            draw.ellipse(
                [lx - lr, ly - lr, lx + lr, ly + lr], fill="#FFF8EF", outline=FRAME_COLOR, width=4
            )
            draw.text(
                (lx, ly), letter, font=_cjk_font(int(lr * 1.15)), fill=TEXT_COLOR, anchor="mm"
            )

        paw = _paw_print(int(badge_size * 0.5), cell["badge_color"]).rotate(20, expand=True)
        image.paste(
            paw, (int(bx - badge_size * 0.62 - paw.width / 2), int(by + badge_size * 0.08)), paw
        )
        star_img = _star(int(badge_size * 0.30), STAR_COLOR)
        image.paste(star_img, (int(bx + badge_size * 0.42), int(by - badge_size * 0.55)), star_img)

        lines = _wrap_label(cell["label"])
        line_height = 78
        # Measured from the badge's actual bottom edge (not scaled by `half`)
        # so narrow columns — where `half` shrinks independently of `by` —
        # can't collapse this gap to zero and overlap the icon.
        badge_bottom = by + half
        start_y = badge_bottom + 30 + line_height / 2
        for line_index, line in enumerate(lines):
            draw.text(
                (bx, start_y + line_index * line_height),
                line,
                font=label_font,
                fill=TEXT_COLOR,
                anchor="mm",
            )

    for area in areas:
        bounds = area["bounds"]
        x0, y0 = bounds["x"], bounds["y"]
        x1, y1 = x0 + bounds["width"], y0 + bounds["height"]
        if x1 < WIDTH:
            draw.line([x1, y0, x1, y1], fill=FRAME_COLOR, width=DIVIDER_WIDTH)
        if y1 < HEIGHT:
            draw.line([x0, y1, x1, y1], fill=FRAME_COLOR, width=DIVIDER_WIDTH)

    draw.rounded_rectangle(
        [FRAME_INSET, FRAME_INSET, WIDTH - FRAME_INSET, HEIGHT - FRAME_INSET],
        radius=FRAME_RADIUS,
        outline=FRAME_COLOR,
        width=FRAME_WIDTH,
    )

    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("infra/local/line-rich-menu.yaml"))
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    document = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    menus = document.get("menus", [])
    if not menus:
        raise SystemExit(f"{args.config} 沒有任何 menus")

    out_dir = args.out_dir or args.config.parent
    for menu in menus:
        actions = menu.get("actions", [])
        if not actions:
            continue
        image = build_image(actions)
        out_path = out_dir / f"line-rich-menu-{menu['key']}.png"
        image.save(out_path, format="PNG")
        print(f"已產生 {out_path}（{WIDTH}x{HEIGHT}，{len(actions)} 個按鈕）")


if __name__ == "__main__":
    main()
