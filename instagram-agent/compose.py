"""Crop the generated photo to Instagram size and add branded text overlay."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

SIZES = {"post": (1080, 1350), "story": (1080, 1920)}

FONT_DIR = Path(__file__).parent / "fonts"
FONT_CANDIDATES = {
    "bold": [
        os.getenv("FONT_BOLD", ""),
        str(FONT_DIR / "bold.ttf"),
        "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "regular": [
        os.getenv("FONT_REGULAR", ""),
        str(FONT_DIR / "regular.ttf"),
        "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit(draw, text, kind, max_w, start, min_size, max_lines):
    size = start
    while size > min_size:
        font = _font(kind, size)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
        size -= 4
    font = _font(kind, min_size)
    return font, _wrap(draw, text, font, max_w)


def compose(image_bytes: bytes, fmt: str, headline: str, subline: str, cta: str,
            brand: dict, text_position: str = "bottom") -> bytes:
    W, H = SIZES[fmt]
    colors = brand["style"]["colors"]
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS, centering=(0.5, 0.4))

    pad = 72
    # Story safe zones: top ~250px and bottom ~340px are covered by IG UI.
    safe_top, safe_bottom = (250, 340) if fmt == "story" else (60, 60)
    max_w = W - 2 * pad

    measure = ImageDraw.Draw(img)
    h_font, h_lines = _fit(measure, headline.upper(), "bold", max_w, 96 if fmt == "story" else 84, 44, 3)
    s_font, s_lines = _fit(measure, subline, "regular", max_w, 42, 28, 3) if subline else (None, [])
    c_font = _font("bold", 36)

    h_lh = int(h_font.size * 1.08)
    s_lh = int(s_font.size * 1.3) if s_font else 0
    cta_h = 84 if cta else 0
    block_h = len(h_lines) * h_lh + (24 + len(s_lines) * s_lh if s_lines else 0) + (36 + cta_h if cta else 0)

    if text_position == "top":
        y0 = safe_top + 20
    else:
        y0 = H - safe_bottom - block_h - 20

    # Soft gradient behind text for legibility, fading out towards the photo.
    if text_position == "top":
        gy, grad_h = 0, y0 + block_h + 200
    else:
        gy = max(0, y0 - 200)
        grad_h = H - gy
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        t = y / grad_h
        grad.putpixel((0, y), int(190 * ((1 - t) if text_position == "top" else t) ** 1.4))
    grad = grad.resize((W, grad_h))
    shade = Image.new("RGB", (W, grad_h), colors["dark"])
    img.paste(shade, (0, gy), grad.filter(ImageFilter.GaussianBlur(8)))

    d = ImageDraw.Draw(img)
    y = y0
    for line in h_lines:
        d.text((pad, y), line, font=h_font, fill="#ffffff")
        y += h_lh
    if s_lines:
        y += 24
        for line in s_lines:
            d.text((pad, y), line, font=s_font, fill=colors["background"])
            y += s_lh
    if cta:
        y += 36
        tw = d.textlength(cta, font=c_font)
        d.rounded_rectangle([pad, y, pad + tw + 64, y + cta_h - 12], radius=36, fill=colors["accent"])
        d.text((pad + 32, y + (cta_h - 12) / 2), cta, font=c_font, fill=colors["dark"], anchor="lm")

    # Small brand mark in the corner.
    m_font = _font("bold", 26)
    my = safe_top - 10 if fmt == "story" else 48
    if text_position == "top":
        my = H - safe_bottom - 30
    # Lime asterisk-like mark (drawn, so it does not depend on font glyph coverage).
    cx, cy, r = pad + 12, my + 13, 12
    for ang in (0, 45, 90, 135):
        dx, dy = r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang))
        d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=colors["accent"], width=5)
    d.text((pad + 36, my), brand["name"].upper(), font=m_font, fill="#ffffff",
           stroke_width=2, stroke_fill=colors["dark"])

    out = io.BytesIO()
    img.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()
