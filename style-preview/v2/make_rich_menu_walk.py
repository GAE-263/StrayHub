"""Draw a Rich Menu in the block-sticker style: cream ground, chocolate outlines,
flat offset shadows, big radii.

A Rich Menu is a flat image, so unlike Flex this style can be reproduced exactly
— shadows and all. Sizes are expressed in CSS pixels and scaled up, because the
2500px artwork is displayed around 400px wide on a phone; a literal 4px border
would be invisible.

    python make_rich_menu_sticker.py <output.png>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 2500, 1686
# One full-width hero across the top, two half-width cells beneath it.
# Fractions of the canvas, so the same numbers describe the tap areas.
LAYOUT = [
    (0.0, 0.0, 1.0, 0.5),
    (0.0, 0.5, 0.5, 0.5),
    (0.5, 0.5, 0.5, 0.5),
]
SS = 2  # supersample factor, downscaled once at the end for clean curves

# The artwork is shown at roughly 400px wide, so CSS sizes are scaled to match.
PHONE_WIDTH = 400
CSS = WIDTH / PHONE_WIDTH

CREAM = (250, 246, 238)
SURFACE = (255, 252, 243)
INK = (113, 96, 83)
LEAF = (168, 198, 159)
BUTTER = (246, 215, 122)
PEACH = (242, 184, 162)
SKY = (169, 201, 219)

TILES = [
    {"label": "開始散步回報", "sub": "WALK", "fill": BUTTER, "icon": "paw", "hero": True},
    {"label": "繼續回報", "sub": "RESUME", "fill": PEACH, "icon": "arrow", "hero": False},
    {"label": "聯絡工作人員", "sub": "CONTACT", "fill": SKY, "icon": "chat", "hero": False},
]

FONTS = [r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc"]
LATIN = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf"]


def px(css: float) -> int:
    """CSS pixels to artwork pixels, at supersampled scale."""
    return round(css * CSS * SS)


def font(size_css: float, latin: bool = False) -> ImageFont.FreeTypeFont:
    size = px(size_css)
    for path in LATIN if latin else FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def centred(draw, xy, text, fnt, fill) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(
        (xy[0] - (box[2] - box[0]) / 2 - box[0], xy[1] - (box[3] - box[1]) / 2 - box[1]),
        text,
        font=fnt,
        fill=fill,
    )


def sticker(draw, box, radius, fill, *, border_css: float = 4, offset_css: float = 4) -> None:
    """A filled rounded rect with a hard, unblurred offset shadow behind it."""
    x0, y0, x1, y1 = box
    d = px(offset_css)
    draw.rounded_rectangle([x0 + d, y0 + d, x1 + d, y1 + d], radius=radius, fill=INK)
    draw.rounded_rectangle(
        [x0, y0, x1, y1], radius=radius, fill=fill, outline=INK, width=px(border_css)
    )


def draw_icon(draw, kind, cx, cy, s) -> None:
    """Simple geometry in ink, sized relative to the badge."""
    if kind == "paw":
        draw.ellipse([cx - s * 0.34, cy - s * 0.02, cx + s * 0.34, cy + s * 0.52], fill=INK)
        for dx, dy in ((-0.44, -0.26), (-0.15, -0.47), (0.15, -0.47), (0.44, -0.26)):
            r = s * 0.15
            draw.ellipse(
                [cx + s * dx - r, cy + s * dy - r, cx + s * dx + r, cy + s * dy + r], fill=INK
            )
    elif kind == "dog":
        # Long drooping ears and a lower muzzle, so it does not read as a bear.
        for side in (-1, 1):
            draw.ellipse(
                [
                    cx + side * s * 0.42 - s * 0.19,
                    cy - s * 0.46,
                    cx + side * s * 0.42 + s * 0.19,
                    cy + s * 0.34,
                ],
                fill=INK,
            )
        draw.ellipse([cx - s * 0.38, cy - s * 0.40, cx + s * 0.38, cy + s * 0.30], fill=INK)
        draw.ellipse([cx - s * 0.24, cy + s * 0.02, cx + s * 0.24, cy + s * 0.46], fill=INK)
        for side in (-1, 1):
            draw.ellipse(
                [
                    cx + side * s * 0.17 - s * 0.055,
                    cy - s * 0.20,
                    cx + side * s * 0.17 + s * 0.055,
                    cy - s * 0.08,
                ],
                fill=CREAM,
            )
        draw.ellipse([cx - s * 0.075, cy + s * 0.10, cx + s * 0.075, cy + s * 0.22], fill=CREAM)
    elif kind == "arrow":
        draw.ellipse(
            [cx - s * 0.50, cy - s * 0.50, cx + s * 0.50, cy + s * 0.50],
            outline=INK,
            width=px(3.5),
        )
        draw.polygon(
            [(cx - s * 0.13, cy - s * 0.26), (cx + s * 0.27, cy), (cx - s * 0.13, cy + s * 0.26)],
            fill=INK,
        )
    elif kind == "chat":
        draw.rounded_rectangle(
            [cx - s * 0.50, cy - s * 0.42, cx + s * 0.50, cy + s * 0.24],
            radius=s * 0.22,
            outline=INK,
            width=px(3.5),
        )
        draw.polygon(
            [
                (cx - s * 0.20, cy + s * 0.18),
                (cx + s * 0.02, cy + s * 0.18),
                (cx - s * 0.26, cy + s * 0.54),
            ],
            fill=INK,
        )
        for dx in (-0.20, 0.0, 0.20):
            r = s * 0.065
            draw.ellipse(
                [cx + s * dx - r, cy - s * 0.12 - r, cx + s * dx + r, cy - s * 0.12 + r], fill=INK
            )


def confetti(draw, w, h) -> None:
    """Outlined dots tucked into the gutter cross, deterministic so reruns match.

    They stay clear of the card edges: anything near the outer border gets
    clipped by the canvas and reads as a mistake rather than a flourish.
    """
    spots = [
        (0.50, 0.24, 13, PEACH),
        (0.50, 0.50, 20, BUTTER),
        (0.50, 0.76, 13, LEAF),
        (0.22, 0.50, 11, SKY),
        (0.78, 0.50, 11, PEACH),
    ]
    for fx, fy, r_css, colour in spots:
        cx, cy, r = w * fx, h * fy, px(r_css)
        draw.ellipse([cx + px(2) - r, cy + px(2) - r, cx + px(2) + r, cy + px(2) + r], fill=INK)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=INK, width=px(2.5))


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "rich-menu-sticker.png")
    W, H = WIDTH * SS, HEIGHT * SS

    image = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(image)
    # No confetti here: the hero plus two cells fill the canvas, so stray dots
    # only peek out from behind the cards and read as a mistake.

    gutter = px(7)
    radius = px(24)
    badge_radius = px(18)

    hero_font, hero_sub = font(21), font(9, latin=True)
    tile_font, tile_sub = font(15), font(7.5, latin=True)

    for tile, (fx, fy, fw, fh) in zip(TILES, LAYOUT, strict=True):
        x0 = W * fx + gutter
        y0 = H * fy + gutter
        x1 = W * (fx + fw) - gutter - px(4)
        y1 = H * (fy + fh) - gutter - px(4)

        sticker(draw, (x0, y0, x1, y1), radius, SURFACE, border_css=5, offset_css=5)

        if tile["hero"]:
            # Wide row: badge to the left of a centred label.
            cy = (y0 + y1) / 2
            badge = px(52)
            bx = x0 + (x1 - x0) * 0.13
            sticker(
                draw,
                (bx - badge / 2, cy - badge / 2, bx + badge / 2, cy + badge / 2),
                badge_radius,
                tile["fill"],
                border_css=4,
                offset_css=4,
            )
            draw_icon(draw, tile["icon"], bx, cy, badge * 0.36)
            text_cx = (bx + badge / 2 + x1) / 2
            centred(draw, (text_cx, cy - px(7)), tile["label"], hero_font, INK)
            centred(draw, (text_cx, cy + px(16)), tile["sub"], hero_sub, INK)
        else:
            # Narrow cell: badge stacked above the label.
            cx = (x0 + x1) / 2
            badge = px(44)
            by = y0 + (y1 - y0) * 0.34
            sticker(
                draw,
                (cx - badge / 2, by - badge / 2, cx + badge / 2, by + badge / 2),
                badge_radius,
                tile["fill"],
                border_css=4,
                offset_css=4,
            )
            draw_icon(draw, tile["icon"], cx, by, badge * 0.36)
            centred(draw, (cx, y0 + (y1 - y0) * 0.68), tile["label"], tile_font, INK)
            centred(draw, (cx, y0 + (y1 - y0) * 0.83), tile["sub"], tile_sub, INK)

    image = image.resize((WIDTH, HEIGHT), Image.LANCZOS)
    image.save(out, format="PNG", optimize=True)
    kb = out.stat().st_size / 1024
    print(f"wrote {out.name}  {WIDTH}x{HEIGHT}  {kb:.0f} KB")
    if kb > 1024:
        alt = out.with_suffix(".jpg")
        image.save(alt, format="JPEG", quality=90, optimize=True, subsampling=0)
        print(f"      PNG over 1 MB; also wrote {alt.name} at {alt.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
