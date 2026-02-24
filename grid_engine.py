"""
Photo Grid Engine
- Identifies aspect ratios of all photos
- Arranges in a grid prioritizing minimal crop loss
- Output AR is flexible (1:2 to 2:1), not forced 1:1
- Overlays item_name in Cairo font (bottom-left)
"""
import os
import math
import glob
import logging
import requests
import concurrent.futures
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

logger = logging.getLogger("photo-grid-api")


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
    Crop loss is the dominant factor; AR deviation is a mild tiebreaker.
    """
    crop_loss = sum(
        compute_crop_loss(images[idx].width, images[idx].height, cw, ch)
        for (x, y, cw, ch, idx) in cells
        if cw > 0 and ch > 0
    )
    output_ar = canvas_w / canvas_h
    ar_penalty = abs(output_ar - 1.0) * 0.3
    return crop_loss + ar_penalty


# AR limits — output can range from 1:2 (tall) to 2:1 (wide)
MIN_AR = 0.5
MAX_AR = 2.0


def _clamp_ar(width: int, height: int) -> tuple[int, int]:
    """Clamp canvas dimensions to stay within MIN_AR..MAX_AR."""
    ar = width / height
    if ar > MAX_AR:
        height = int(width / MAX_AR)
    elif ar < MIN_AR:
        width = int(height * MIN_AR)
    return width, height


def find_best_layout(images: list, target_size: int = 1200) -> dict:
    """
    Find the grid layout that minimizes crop loss.
    Output aspect ratio is flexible (up to 2:1 or 1:2).
    """
    n = len(images)
    gap = 4

    if n == 1:
        img = images[0]
        ar = img.width / img.height
        ar = max(MIN_AR, min(MAX_AR, ar))
        if ar >= 1.0:
            w = target_size
            h = int(target_size / ar)
        else:
            h = target_size
            w = int(target_size * ar)
        return {
            "type": "single", "width": w, "height": h,
            "gap": 0, "cells": [(0, 0, w, h, 0)],
        }

    best_score = float("inf")
    best_layout = None

    # Height multipliers to sweep — allows canvas to be shorter or taller
    height_factors = [x / 100.0 for x in range(50, 151, 5)]

    if n == 2:
        # Side by side — sweep split ratio AND canvas height
        for h_factor in height_factors:
            h = int(target_size * h_factor)
            if h < 100:
                continue
            for split_pct in [x / 100.0 for x in range(20, 81, 2)]:
                w0 = int(target_size * split_pct) - gap // 2
                w1 = target_size - w0 - gap
                if w0 < 50 or w1 < 50:
                    continue
                cw, ch = _clamp_ar(target_size, h)
                # Recompute cell heights after clamp
                cell_h = ch
                cells = [(0, 0, w0, cell_h, 0), (w0 + gap, 0, w1, cell_h, 1)]
                sc = score_layout(images, cells, cw, ch)
                if sc < best_score:
                    best_score = sc
                    best_layout = {"type": "side_by_side", "width": cw, "height": ch, "gap": gap, "cells": cells}

        # Stacked — sweep split ratio AND canvas width
        for w_factor in height_factors:
            w = int(target_size * w_factor)
            if w < 100:
                continue
            for split_pct in [x / 100.0 for x in range(20, 81, 2)]:
                h0 = int(target_size * split_pct) - gap // 2
                h1 = target_size - h0 - gap
                if h0 < 50 or h1 < 50:
                    continue
                total_h = h0 + gap + h1
                cw, ch = _clamp_ar(w, total_h)
                cells = [(0, 0, cw, h0, 0), (0, h0 + gap, cw, h1, 1)]
                sc = score_layout(images, cells, cw, ch)
                if sc < best_score:
                    best_score = sc
                    best_layout = {"type": "stacked", "width": cw, "height": ch, "gap": gap, "cells": cells}

    elif n == 3:
        for big_idx in range(3):
            small_indices = [i for i in range(3) if i != big_idx]

            # Big LEFT, two stacked RIGHT — sweep total height
            for h_factor in height_factors:
                total_h = int(target_size * h_factor)
                if total_h < 100:
                    continue
                for f in [x / 100.0 for x in range(30, 71, 2)]:
                    w_big = int(target_size * f) - gap // 2
                    w_small = target_size - w_big - gap
                    for split_v in [x / 100.0 for x in range(25, 76, 5)]:
                        h_s0 = int(total_h * split_v) - gap // 2
                        h_s1 = total_h - h_s0 - gap
                        if w_big < 50 or w_small < 50 or h_s0 < 50 or h_s1 < 50:
                            continue
                        cw, ch = _clamp_ar(target_size, total_h)
                        cells = [
                            (0, 0, w_big, total_h, big_idx),
                            (w_big + gap, 0, w_small, h_s0, small_indices[0]),
                            (w_big + gap, h_s0 + gap, w_small, h_s1, small_indices[1]),
                        ]
                        sc = score_layout(images, cells, cw, ch)
                        if sc < best_score:
                            best_score = sc
                            best_layout = {"type": "1big_2small_LR", "width": target_size, "height": total_h, "gap": gap, "cells": cells}

            # Big TOP, two side by side BOTTOM — sweep total height
            for h_factor in height_factors:
                total_h = int(target_size * h_factor)
                if total_h < 100:
                    continue
                for f in [x / 100.0 for x in range(30, 71, 2)]:
                    h_big = int(total_h * f) - gap // 2
                    h_small = total_h - h_big - gap
                    total_w = target_size
                    for split_h in [x / 100.0 for x in range(25, 76, 5)]:
                        w_s0 = int(total_w * split_h) - gap // 2
                        w_s1 = total_w - w_s0 - gap
                        if h_big < 50 or h_small < 50 or w_s0 < 50 or w_s1 < 50:
                            continue
                        cw, ch = _clamp_ar(total_w, total_h)
                        cells = [
                            (0, 0, total_w, h_big, big_idx),
                            (0, h_big + gap, w_s0, h_small, small_indices[0]),
                            (w_s0 + gap, h_big + gap, w_s1, h_small, small_indices[1]),
                        ]
                        sc = score_layout(images, cells, cw, ch)
                        if sc < best_score:
                            best_score = sc
                            best_layout = {"type": "1big_2small_TB", "width": total_w, "height": total_h, "gap": gap, "cells": cells}

    elif n == 4:
        # Sweep canvas height to find best fit for the 4 images
        for h_factor in height_factors:
            total_h = int(target_size * h_factor)
            if total_h < 100:
                continue
            cell_w = (target_size - gap) // 2
            cell_h = (total_h - gap) // 2
            if cell_w < 50 or cell_h < 50:
                continue
            cw, ch = _clamp_ar(target_size, total_h)
            cells = []
            for idx in range(4):
                r, c = divmod(idx, 2)
                cells.append((c * (cell_w + gap), r * (cell_h + gap), cell_w, cell_h, idx))
            sc = score_layout(images, cells, cw, ch)
            if sc < best_score:
                best_score = sc
                best_layout = {"type": "grid_2x2", "width": target_size, "height": total_h, "gap": gap, "cells": cells}

    else:
        # For N>4, derive row height from average image aspect ratio
        avg_ar = sum(img.width / img.height for img in images) / n
        cols = round(math.sqrt(n))
        rows = math.ceil(n / cols)
        cell_w = (target_size - gap * (cols - 1)) // cols
        cell_h = max(int(cell_w / avg_ar), 50)
        total_h = cell_h * rows + gap * (rows - 1)
        cw, ch = _clamp_ar(target_size, total_h)
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

    # Use Pillow's native Raqm layout for Arabic text shaping
    kwargs = {"font": font, "direction": "rtl", "language": "ar"}
    bbox = draw.textbbox((0, 0), text, **kwargs)
    
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
    
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), **kwargs)

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
    
    # Use ThreadPoolExecutor for concurrent downloads
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, max(1, len(photo_urls)))) as executor:
        # Keep original order while downloading concurrently
        futures = [executor.submit(download_image, url) for url in photo_urls]
        for future in futures:
            try:
                img = future.result()
                images.append(img)
            except Exception as e:
                logger.warning(f"Failed to download image: {e}")

    if not images:
        raise ValueError("All images failed to download or no images provided")

    layout = find_best_layout(images, target_size)
    canvas = render_grid(images, layout)
    canvas = overlay_text(canvas, item_name, font_path)

    buf = BytesIO()
    canvas.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return buf.getvalue()
