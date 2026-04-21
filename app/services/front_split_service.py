"""Create front-left/front-right motif assets from the primary white-background image."""
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps


WHITE_MIN = 235
WHITE_SPREAD_MAX = 18
WHITE_DISTANCE_MAX = 42
MIN_SUBJECT_AREA_RATIO = 0.03
MIN_INTERNAL_BG_AREA_RATIO = 0.00012


def _is_white_background_pixel(pixel: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> bool:
    r, g, b = pixel
    if min(pixel) < WHITE_MIN:
        return False
    if max(pixel) - min(pixel) > WHITE_SPREAD_MAX:
        return False
    if not palette:
        return True
    return any(abs(r - pr) + abs(g - pg) + abs(b - pb) <= WHITE_DISTANCE_MAX for pr, pg, pb in palette)


def _edge_pixels(rgb: Image.Image) -> list[tuple[int, int, int]]:
    w, h = rgb.size
    step = max(1, min(w, h) // 96)
    pixels = rgb.load()
    out = []
    for x in range(0, w, step):
        out.append(pixels[x, 0])
        out.append(pixels[x, h - 1])
    for y in range(0, h, step):
        out.append(pixels[0, y])
        out.append(pixels[w - 1, y])
    return out


def _edge_background_palette(rgb: Image.Image) -> list[tuple[int, int, int]]:
    samples = [c for c in _edge_pixels(rgb) if min(c) >= WHITE_MIN and max(c) - min(c) <= WHITE_SPREAD_MAX]
    if not samples:
        return []
    counts: dict[tuple[int, int, int], int] = {}
    for sample in samples:
        bucket = tuple(round(v / 8) * 8 for v in sample)
        counts[bucket] = counts.get(bucket, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    total = max(1, len(samples))
    return [color for color, count in ranked[:6] if count / total >= 0.03]


def _extract_white_background_mask(rgb: Image.Image) -> Image.Image:
    w, h = rgb.size
    palette = _edge_background_palette(rgb)
    pixels = rgb.load()
    mask = Image.new("L", (w, h), 0)
    mask_px = mask.load()
    queue: deque[int] = deque()
    seen = bytearray(w * h)
    for x in range(w):
        queue.append(x)
        queue.append((h - 1) * w + x)
    for y in range(h):
        queue.append(y * w)
        queue.append(y * w + (w - 1))
    while queue:
        idx = queue.popleft()
        if idx < 0 or idx >= len(seen) or seen[idx]:
            continue
        seen[idx] = 1
        x = idx % w
        y = idx // w
        if not _is_white_background_pixel(pixels[x, y], palette):
            continue
        mask_px[x, y] = 255
        if x > 0:
            queue.append(idx - 1)
        if x + 1 < w:
            queue.append(idx + 1)
        if y > 0:
            queue.append(idx - w)
        if y + 1 < h:
            queue.append(idx + w)
    return mask


def _fill_enclosed_white_holes(rgb: Image.Image, bg_mask: Image.Image) -> Image.Image:
    """Promote enclosed white islands to background.

    This catches white pockets trapped between subject parts, such as the area
    between a hand-held prop and the body, that edge flood-fill cannot reach.
    """
    w, h = rgb.size
    palette = _edge_background_palette(rgb)
    pixels = rgb.load()
    bg_px = bg_mask.load()
    seen = bytearray(w * h)
    min_area = max(24, round(w * h * MIN_INTERNAL_BG_AREA_RATIO))

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if seen[idx] or bg_px[x, y] > 0:
                continue
            if not _is_white_background_pixel(pixels[x, y], palette):
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            component: list[tuple[int, int]] = []
            touches_border = False

            while queue:
                cx, cy = queue.popleft()
                cidx = cy * w + cx
                if seen[cidx]:
                    continue
                seen[cidx] = 1
                if bg_px[cx, cy] > 0:
                    continue
                if not _is_white_background_pixel(pixels[cx, cy], palette):
                    continue

                component.append((cx, cy))
                if cx == 0 or cy == 0 or cx == w - 1 or cy == h - 1:
                    touches_border = True

                if cx > 0:
                    queue.append((cx - 1, cy))
                if cx + 1 < w:
                    queue.append((cx + 1, cy))
                if cy > 0:
                    queue.append((cx, cy - 1))
                if cy + 1 < h:
                    queue.append((cx, cy + 1))

            if touches_border or len(component) < min_area:
                continue
            for cx, cy in component:
                bg_px[cx, cy] = 255

    return bg_mask


def _foreground_mask_from_white_bg(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    bg_mask = _extract_white_background_mask(rgb)
    bg_mask = _fill_enclosed_white_holes(rgb, bg_mask)
    subject = ImageOps.invert(bg_mask)
    # Keep this cleanup deliberately light. Aggressive max/min morphology tends
    # to seal narrow background gaps around fingers and props, leaving visible
    # white pockets in the final overlay.
    subject = subject.filter(ImageFilter.MedianFilter(size=3))
    subject = subject.point(lambda value: 255 if value >= 18 else 0)
    return subject


def _decontaminate_white_matte(rgba: Image.Image) -> Image.Image:
    """Remove white matte spill from semi-transparent edge pixels."""
    out = rgba.convert("RGBA")
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a <= 0 or a >= 255:
                continue
            nr = max(0, min(255, round(255 * (r - 255 + a) / a)))
            ng = max(0, min(255, round(255 * (g - 255 + a) / a)))
            nb = max(0, min(255, round(255 * (b - 255 + a) / a)))
            px[x, y] = (nr, ng, nb, a)
    return out


def _alpha_bbox(alpha: Image.Image) -> tuple[int, int, int, int] | None:
    bbox = alpha.getbbox()
    if not bbox:
        return None
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if area <= 0:
        return None
    return bbox


def _coarse_bbox_from_background_diff(img: Image.Image) -> tuple[int, int, int, int] | None:
    rgb = img.convert("RGB")
    bg = _edge_background_palette(rgb)
    if not bg:
        bg = [(248, 248, 248)]
    pixels = rgb.load()
    w, h = rgb.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if not _is_white_background_pixel(pixels[x, y], bg):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if area < w * h * MIN_SUBJECT_AREA_RATIO:
        return None
    return bbox


def _build_soft_subject_rgba(img: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image]:
    rgba = img.convert("RGBA")
    coarse_mask = _foreground_mask_from_white_bg(rgba)
    bbox = _alpha_bbox(coarse_mask)
    if not bbox:
        bbox = _coarse_bbox_from_background_diff(rgba)
    if not bbox:
        fallback = Image.new("L", rgba.size, 255)
        return rgba, fallback, Image.new("RGBA", rgba.size, (255, 255, 255, 0))

    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if area < rgba.width * rgba.height * MIN_SUBJECT_AREA_RATIO:
        fallback_bbox = _coarse_bbox_from_background_diff(rgba)
        if fallback_bbox:
            bbox = fallback_bbox

    hard_mask = coarse_mask.point(lambda value: 255 if value >= 20 else 0)
    alpha = hard_mask.filter(ImageFilter.GaussianBlur(radius=1.35))
    alpha = ImageChops.lighter(alpha, hard_mask)
    alpha = alpha.point(lambda value: 0 if value <= 8 else min(255, int(value * 1.08)))

    bbox = _alpha_bbox(alpha)
    if not bbox:
        bbox = _coarse_bbox_from_background_diff(rgba)
        if not bbox:
            fallback = Image.new("L", rgba.size, 255)
            return rgba, fallback, Image.new("RGBA", rgba.size, (255, 255, 255, 0))
        alpha = Image.new("L", rgba.size, 0)
        alpha.paste(255, bbox)

    out = rgba.copy()
    out.putalpha(alpha)
    out = _decontaminate_white_matte(out)
    overlay = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    overlay.paste((255, 0, 0, 96), mask=hard_mask)
    return out, alpha, overlay


def _crop_subject(img: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image]:
    rgba, alpha, overlay = _build_soft_subject_rgba(img)
    w, h = rgba.size
    bbox = _alpha_bbox(alpha)
    if not bbox:
        side_w = round(w * 0.82)
        side_h = round(h * 0.82)
        left = max(0, (w - side_w) // 2)
        top = max(0, (h - side_h) // 2)
        bbox = (left, top, min(w, left + side_w), min(h, top + side_h))
    pad = max(8, round(min(w, h) * 0.04))
    top_pad = max(pad, round(min(w, h) * 0.08))
    bottom_pad = max(pad, round(min(w, h) * 0.05))
    bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - top_pad),
        min(w, bbox[2] + pad),
        min(h, bbox[3] + bottom_pad),
    )
    cropped = rgba.crop(bbox)
    margin_x = max(6, round(cropped.width * 0.035))
    margin_top = max(12, round(cropped.height * 0.08))
    margin_bottom = max(8, round(cropped.height * 0.04))
    out = Image.new(
        "RGBA",
        (cropped.width + margin_x * 2, cropped.height + margin_top + margin_bottom),
        (0, 0, 0, 0),
    )
    out.alpha_composite(cropped, (margin_x, margin_top))
    return out, alpha, overlay


def _crop_half_to_seam_alpha(half: Image.Image, seam_side: str) -> Image.Image:
    """Trim transparent padding so the visible half touches the seam edge."""
    rgba = half.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        return rgba
    pad = max(2, round(min(rgba.size) * 0.015))
    top_pad = max(pad, round(min(rgba.size) * 0.06))
    bottom_pad = max(pad, round(min(rgba.size) * 0.035))
    top = max(0, bbox[1] - top_pad)
    bottom = min(rgba.height, bbox[3] + bottom_pad)
    if seam_side == "right":
        left = max(0, bbox[0] - pad)
        right = bbox[2]
    else:
        left = bbox[0]
        right = min(rgba.width, bbox[2] + pad)
    if right <= left or bottom <= top:
        return rgba
    return rgba.crop((left, top, right, bottom))


def create_front_split_assets(theme_image: str | Path, out_dir: str | Path) -> dict:
    """Crop the primary subject and create full-front plus legacy split motifs."""
    out_dir = Path(out_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(theme_image) as src:
        subject, mask, overlay = _crop_subject(src)

    full_path = assets_dir / "theme_front_full.png"
    mask_path = assets_dir / "theme_front_mask.png"
    overlay_path = assets_dir / "theme_front_debug_overlay.png"
    subject.save(full_path)
    mask.save(mask_path)
    overlay.save(overlay_path)

    mid = max(1, subject.width // 2)
    overlap = min(8, max(2, round(subject.width * 0.01))) if subject.width > 4 else 0
    left = subject.crop((0, 0, min(subject.width, mid + overlap), subject.height))
    right = subject.crop((max(0, mid - overlap), 0, subject.width, subject.height))
    left = _crop_half_to_seam_alpha(left, "right")
    right = _crop_half_to_seam_alpha(right, "left")
    left_path = assets_dir / "theme_front_left.png"
    right_path = assets_dir / "theme_front_right.png"
    left.save(left_path)
    right.save(right_path)
    return {
        "full": str(full_path.resolve()),
        "left": str(left_path.resolve()),
        "right": str(right_path.resolve()),
        "source": str(Path(theme_image).resolve()),
        "split_overlap_px": overlap,
    }


def inject_front_split_motifs(texture_set_path: str | Path, split_assets: dict) -> Path:
    """Register generated front motifs in texture_set.json."""
    path = Path(texture_set_path)
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("False", "false").replace("True", "true")
        data = json.loads(text)
    full_path = split_assets.get("full") or split_assets.get("source")
    left_path = split_assets.get("left")
    right_path = split_assets.get("right")
    if not full_path or not left_path or not right_path:
        data["theme_front_split"] = split_assets
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    motifs = [
        m for m in data.get("motifs", [])
        if m.get("motif_id") not in {"theme_front_full", "theme_front_left", "theme_front_right"}
    ]
    motifs.extend([
        {
            "motif_id": "theme_front_full",
            "texture_id": "theme_front_full",
            "path": full_path,
            "role": "front_full_theme",
            "approved": True,
            "candidate": False,
            "prompt": "主题/AI主图主体完整前身画布，程序生成",
            "model": "deterministic-theme-front-full",
            "seed": "",
        },
        {
            "motif_id": "theme_front_left",
            "texture_id": "theme_front_left",
            "path": left_path,
            "role": "front_left_theme",
            "approved": True,
            "candidate": False,
            "prompt": "主题/AI主图主体左半，程序生成",
            "model": "deterministic-theme-split",
            "seed": "",
        },
        {
            "motif_id": "theme_front_right",
            "texture_id": "theme_front_right",
            "path": right_path,
            "role": "front_right_theme",
            "approved": True,
            "candidate": False,
            "prompt": "主题/AI主图主体右半，程序生成",
            "model": "deterministic-theme-split",
            "seed": "",
        },
    ])
    data["motifs"] = motifs
    data["theme_front_split"] = split_assets
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
