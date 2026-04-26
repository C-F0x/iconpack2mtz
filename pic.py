# -*- coding: utf-8 -*-
"""
Preview image generation for MTZ themes.
Produces three JPEG previews with gradient backgrounds and randomly sampled icons.

Dependencies: Pillow  (pip install Pillow)
"""

import colorsys
import io
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from utils import log

# ── Preview specs ─────────────────────────────────────────────────────────────
#   (filename, width, height, cols, rows)
PREVIEW_SPECS: list[tuple[str, int, int, int, int]] = [
    ("preview_icons_2x3_0.jpg",  486,  320, 2, 3),
    ("preview_icons_4x3_0.jpg",  486,  627, 4, 3),
    ("preview_icons_0.jpg",     1080, 2340, 4, 7),
]

JPEG_QUALITY  = 92
ICON_PADDING  = 0.15   # fraction of cell size used as padding around each icon
SHADOW_RADIUS = 6      # px — drop-shadow blur for icons
SHADOW_OFFSET = (3, 3) # px


# ── Colour helpers ────────────────────────────────────────────────────────────

def _random_palette() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """
    Return two dark RGB colours for a gradient.
    Uses HSV with randomised hue for natural-looking pairs.
    """
    hue1 = random.random()
    hue2 = (hue1 + random.uniform(0.08, 0.25)) % 1.0
    sat  = random.uniform(0.45, 0.75)
    val  = random.uniform(0.20, 0.40)   # dark background

    def hsv_to_rgb8(h: float, s: float, v: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (int(r * 255), int(g * 255), int(b * 255))

    c1 = hsv_to_rgb8(hue1, sat, val)
    c2 = hsv_to_rgb8(hue2, sat, val + 0.08)
    return c1, c2


# ── Background generation ─────────────────────────────────────────────────────

def _make_gradient_background(w: int, h: int) -> Image.Image:
    """
    Diagonal linear gradient with a soft radial glow at the centre.
    Returns an RGB PIL Image.
    """
    c1, c2 = _random_palette()

    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    t = (xv + yv) / 2.0   # diagonal blend [0..1]

    r = (c1[0] * (1.0 - t) + c2[0] * t).astype(np.uint8)
    g = (c1[1] * (1.0 - t) + c2[1] * t).astype(np.uint8)
    b = (c1[2] * (1.0 - t) + c2[2] * t).astype(np.uint8)

    img = Image.fromarray(np.stack([r, g, b], axis=2), "RGB")

    # Soft radial glow via concentric ellipses + blur
    cx, cy   = w // 2, h // 2
    glow_r   = min(w, h) * 0.55
    glow_img = Image.new("RGB", (w, h), (0, 0, 0))
    draw     = ImageDraw.Draw(glow_img)
    steps    = 24
    for i in range(steps, 0, -1):
        alpha = int(35 * (i / steps) ** 2)
        r_px  = int(glow_r * i / steps)
        draw.ellipse(
            [cx - r_px, cy - r_px, cx + r_px, cy + r_px],
            fill=(alpha, alpha, alpha),
        )
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=glow_r * 0.3))

    # Screen blend: out = 1 - (1-base)*(1-glow)
    arr_base = np.array(img,      dtype=np.float32) / 255.0
    arr_glow = np.array(glow_img, dtype=np.float32) / 255.0
    arr_out  = 1.0 - (1.0 - arr_base) * (1.0 - arr_glow)
    return Image.fromarray((arr_out * 255).astype(np.uint8), "RGB")


# ── Icon compositing ──────────────────────────────────────────────────────────

def _icon_with_shadow(icon: Image.Image, size: int) -> Image.Image:
    """
    Resize icon to size×size and add a soft drop-shadow.
    Returns an RGBA image with a small margin for the shadow.
    """
    margin = SHADOW_RADIUS * 2 + max(abs(SHADOW_OFFSET[0]), abs(SHADOW_OFFSET[1]))
    canvas = Image.new("RGBA", (size + margin, size + margin), (0, 0, 0, 0))

    icon_r     = icon.resize((size, size), Image.LANCZOS).convert("RGBA")
    alpha_only = icon_r.split()[3]

    ox = margin // 2 + SHADOW_OFFSET[0]
    oy = margin // 2 + SHADOW_OFFSET[1]
    shadow = Image.new("RGBA", (size + margin, size + margin), (0, 0, 0, 0))
    shadow_col = Image.new("RGBA", (size, size), (0, 0, 0, 120))
    shadow.paste(shadow_col, (ox, oy), mask=alpha_only)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=SHADOW_RADIUS))

    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(icon_r, (margin // 2, margin // 2), mask=icon_r)
    return canvas


def _compose_preview(
    bg: Image.Image,
    icons: list[Image.Image],
    cols: int,
    rows: int,
) -> Image.Image:
    """Place icons in a cols×rows grid centred on bg. Returns RGB image."""
    w, h    = bg.size
    bg_rgba = bg.convert("RGBA")

    cell_w    = w / cols
    cell_h    = h / rows
    icon_size = int(min(cell_w, cell_h) * (1.0 - 2.0 * ICON_PADDING))

    it = iter(icons)
    for row in range(rows):
        for col in range(cols):
            ic = next(it, None)
            if ic is None:
                break
            composed = _icon_with_shadow(ic, icon_size)
            cw, ch   = composed.size
            cx = int(col * cell_w + (cell_w - cw) / 2)
            cy = int(row * cell_h + (cell_h - ch) / 2)
            bg_rgba.paste(composed, (cx, cy), mask=composed)

    return bg_rgba.convert("RGB")


# ── Public API ────────────────────────────────────────────────────────────────

def build_previews(pool: dict[str, bytes]) -> dict[str, bytes]:
    """
    Generate all preview images from the drawable pool.
    Returns {filename: jpeg_bytes}.
    """
    if not pool:
        log.warning("Drawable pool is empty — previews will have no icons.")

    stems   = list(pool.keys())
    results: dict[str, bytes] = {}

    for filename, pw, ph, cols, rows in PREVIEW_SPECS:
        count  = cols * rows
        sample = random.sample(stems, min(count, len(stems)))

        icons: list[Image.Image] = []
        for stem in sample:
            try:
                icons.append(Image.open(io.BytesIO(pool[stem])).convert("RGBA"))
            except Exception as e:
                log.debug(f"Preview: failed to open {stem}: {e}")

        bg      = _make_gradient_background(pw, ph)
        preview = _compose_preview(bg, icons, cols, rows)

        buf = io.BytesIO()
        preview.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        results[filename] = buf.getvalue()

        log.info(f"Preview generated: {filename} ({pw}×{ph}, {len(icons)} icons)")
        print(f"  Preview: {filename}  ({pw}×{ph})")

    return results
