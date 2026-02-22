"""
Photo Grid Engine
- Identifies aspect ratios of all photos
- Arranges in a grid targeting 1:1 output aspect ratio
- Minimizes crop loss
- Overlays item_name in Cairo font (bottom-left)
"""
import os
import math
import glob
import requests
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO


def download_image(url: str, timeout: int = 30) -> Image.Image:
    """Download an image from URL and return as PIL Image."""
    headers = {"User-Agent": "Mozilla/5.0"}
    url = url.replace("&amp;", "&")
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")


def get_aspect_ratio(img: Image.Image) -> float:
    return img.width / img.height


def compute_crop_loss(img_w: int, img_h: int, cell_w: int, cell_h: int) -> float:
    """Fraction of pixels cropped when cover-fitting img into cell."""
    scale = max(cell_w / img_w, cell_h / img_h)
    scaled_w = img_w * scale
    scaled_h = img_h * scale
    return 1.0 - (cell_w * cell_h) / (scaled_w * scaled_h)


def fit_and_crop(img: Image.Image, cell_w: int, cell_h: int) -> Image.Image:
    """Scale image to cover cell, then center-crop to exact cell size."""
    scale = max(cell_w / img.width, cell_h / img.height)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - cell_w) // 2
    top = (new_h - cell_h) // 2
    return img_resized.crop((left, top, left + cell_w, top + cell_h))


def score_layout(images: list, cells: list, canvas_w: int, canvas_h: int) -> float:
    """
    Score a layout. Lower is better.
    Combines crop loss + deviation from 1:1 aspect ratio.
    """
    crop_loss = sum(
        compute_crop_loss(images[idx].width, images[idx].height, cw, ch)
        for (x, y, cw, ch, idx) in cells
        if cw > 0 and ch > 0
    )
    output_ar = canvas_w / canvas_h
    ar_penalty = abs(output_ar - 1.0) * 2.0
    return crop_loss + ar_penalty


def find_best_layout(images: list, target_size: int = 1200) -> dict:
    """
    Find the grid layout closest to 1:1 with minimal crop loss.
    """
    n = len(images)
    gap = 4

    if n == 1:
        return {
            "type": "single", "width": target_size, "height": target_size,
            "gap": 0, "cells": [(0, 0, target_size, target_size, 0)],
        }

    best_score = float("inf")
    best_layout = None

    if n == 2:
        # Side by side — sweep split ratio
        for split_pct in [x / 100.0 for x in range(20, 81, 2)]:
            w0 = int(target_size * split_pct) - gap // 2
            w1 = target_size - w0 - gap
            h = target_size
            if w0 < 50 or w1 < 50:
                continue
            cells = [(0, 0, w0, h, 0), (w0 + gap, 0, w1, h, 1)]
            sc = score_layout(images, cells, target_size, h)
            if sc < best_score:
                best_score = sc
                best_layout = {"type": "side_by_side", "width": target_size, "height": h, "gap": gap, "cells": cells}

        # Stacked — sweep split ratio
        for split_pct in [x / 100.0 for x in range(20, 81, 2)]:
            h0 = int(target_size * split_pct) - gap // 2
            h1 = target_size - h0 - gap
            w = target_size
            if h0 < 50 or h1 < 50:
                continue
            cells = [(0, 0, w, h0, 0), (0, h0 + gap, w, h1, 1)]
            total_h = h0 + gap + h1
            sc = score_layout(images, cells, w, total_h)
            if sc < best_score:
                best_score = sc
                best_layout = {"type": "stacked", "width": w, "height": total_h, "gap": gap, "cells": cells}

    elif n == 3:
        for big_idx in range(3):
            small_indices = [i for i in range(3) if i != big_idx]

            # Big LEFT, two stacked RIGHT
            for f in [x / 100.0 for x in range(30, 71, 2)]:
                w_big = int(target_size * f) - gap // 2
                w_small = target_size - w_big - gap
                total_h = target_size
                for split_v in [x / 100.0 for x in range(25, 76, 5)]:
                    h_s0 = int(total_h * split_v) - gap // 2
                    h_s1 = total_h - h_s0 - gap
                    if w_big < 50 or w_small < 50 or h_s0 < 50 or h_s1 < 50:
                        continue
                    cells = [
                        (0, 0, w_big, total_h, big_idx),
                        (w_big + gap, 0, w_small, h_s0, small_indices[0]),
                        (w_big + gap, h_s0 + gap, w_small, h_s1, small_indices[1]),
                    ]
                    sc = score_layout(images, cells, target_size, total_h)
                    if sc < best_score:
                        best_score = sc
                        best_layout = {"type": "1big_2small_LR", "width": target_size, "height": total_h, "gap": gap, "cells": cells}

            # Big TOP, two side by side BOTTOM
            for f in [x / 100.0 for x in range(30, 71, 2)]:
                h_big = int(target_size * f) - gap // 2
                h_small = target_size - h_big - gap
                total_w = target_size
                for split_h in [x / 100.0 for x in range(25, 76, 5)]:
                    w_s0 = int(total_w * split_h) - gap // 2
                    w_s1 = total_w - w_s0 - gap
                    if h_big < 50 or h_small < 50 or w_s0 < 50 or w_s1 < 50:
                        continue
                    cells = [
                        (0, 0, total_w, h_big, big_idx),
                        (0, h_big + gap, w_s0, h_small, small_indices[0]),
                        (w_s0 + gap, h_big + gap, w_s1, h_small, small_indices[1]),
                    ]
                    sc = score_layout(images, cells, total_w, target_size)
                    if sc < best_score:
                        best_score = sc
                        best_layout = {"type": "1big_2small_TB", "width": total_w, "height": target_size, "gap": gap, "cells": cells}

    elif n == 4:
        cell_w = (target_size - gap) // 2
        cell_h = (target_size - gap) // 2
        cells = []
        for idx in range(4):
            r, c = divmod(idx, 2)
            cells.append((c * (cell_w + gap), r * (cell_h + gap), cell_w, cell_h, idx))
        sc = score_layout(images, cells, target_size, target_size)
        if sc < best_score:
            best_score = sc
            best_layout = {"type": "grid_2x2", "width": target_size, "height": target_size, "gap": gap, "cells": cells}

    else:
        cols = round(math.sqrt(n))
        rows = math.ceil(n / cols)
        cell_w = (target_size - gap * (cols - 1)) // cols
        cell_h = (target_size - gap * (rows - 1)) // rows
        total_h = cell_h * rows + gap * (rows - 1)
        cells = []
        for idx in range(n):
            r = idx // cols
            c = idx % cols
            cells.append((c * (cell_w + gap), r * (cell_h + gap), cell_w, cell_h, idx))
        best_layout = {"type": f"grid_{rows}x{cols}", "width": target_size, "height": total_h, "gap": gap, "cells": cells}

    return best_layout


def render_grid(images: list, layout: dict) -> Image.Image:
    """Render images into the grid layout."""
    canvas = Image.new("RGB", (layout["width"], layout["height"]), (30, 30, 30))
    for (x, y, cw, ch, img_idx) in layout["cells"]:
        cropped = fit_and_crop(images[img_idx], cw, ch)
        canvas.paste(cropped, (x, y))
    return canvas


def _resolve_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont:
    """Find the best available font, preferring Cairo."""
    candidates = [
        font_path,
        "/usr/share/fonts/truetype/cairo/Cairo-Bold.ttf",
        "/usr/share/fonts/truetype/cairo/Cairo-Regular.ttf",
        "/usr/share/fonts/truetype/cairo/Cairo-SemiBold.ttf",
        "/app/fonts/Cairo-Bold.ttf",
        "/app/fonts/Cairo-Regular.ttf",
        "fonts/Cairo-Bold.ttf",
        "fonts/Cairo-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in candidates:
        if fp and os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, font_size)
            except Exception:
                continue

    for pattern in ["/usr/share/fonts/**/Cairo*", "/usr/share/fonts/**/cairo*", "/app/fonts/**/*"]:
        for fp in glob.glob(pattern, recursive=True):
            try:
                return ImageFont.truetype(fp, font_size)
            except Exception:
                continue

    return ImageFont.load_default()


def overlay_text(canvas: Image.Image, text: str, font_path: str = None) -> Image.Image:
    """Overlay item_name text on bottom-left with semi-transparent background."""
    draw = ImageDraw.Draw(canvas)
    font_size = max(28, canvas.width // 25)
    font = _resolve_font(font_path, font_size)

    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    
    # Strip invisible bidi formatting characters that render as empty square boxes
    invisible_chars = ['\u200e', '\u200f', '\u202a', '\u202b', '\u202c', '\u202d', '\u202e']
    for char in invisible_chars:
        bidi_text = bidi_text.replace(char, '')

    bbox = draw.textbbox((0, 0), bidi_text, font=font)
    # textbbox returns (left, top, right, bottom) offset from the anchor (0, 0)
    # The actual visual width and height of the text:
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    padding = 16
    margin = 16

    rect_x0 = margin
    rect_y0 = canvas.height - th - padding * 2 - margin
    rect_x1 = margin + tw + padding * 2
    rect_y1 = canvas.height - margin

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle([rect_x0, rect_y0, rect_x1, rect_y1], radius=10, fill=(0, 0, 0, 180))
    canvas = canvas.convert("RGBA")
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    
    # Calculate exact drawing position to perfectly center the text within the padded block
    # We subtract bbox[0] and bbox[1] to neutralize Pillow's internal anchor offsetting
    text_x = rect_x0 + padding - bbox[0]
    text_y = rect_y0 + padding - bbox[1]
    
    draw.text((text_x, text_y), bidi_text, fill=(255, 255, 255, 255), font=font)

    return canvas.convert("RGB")


def generate_grid(
    photo_urls: list[str],
    item_name: str,
    target_size: int = 1200,
    quality: int = 92,
    font_path: str = None,
) -> bytes:
    """
    Main entry point. Downloads photos, builds grid, returns JPEG bytes.
    """
    images = []
    for url in photo_urls:
        img = download_image(url)
        images.append(img)

    if not images:
        raise ValueError("No images provided")

    layout = find_best_layout(images, target_size)
    canvas = render_grid(images, layout)
    canvas = overlay_text(canvas, item_name, font_path)

    buf = BytesIO()
    canvas.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return buf.getvalue()
