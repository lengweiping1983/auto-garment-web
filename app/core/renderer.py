"""Deterministic garment piece renderer using Pillow.

Ported from scripts/渲染裁片.py — ALL core logic preserved:
- tile_image, transform_texture, apply_opacity, apply_mask
- render_texture_layer, render_solid_layer, render_motif_layer
- render_layered_piece
- render_front_pair (cross-seam alignment)
- smart_motif_placement, compute_motif_visibility
- render_all (with slave mirror optimization)
- compose_preview
"""
import json
import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageOps, ImageStat


def load_json(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("False", "false").replace("True", "true")
        return json.loads(text)


def approved_textures(texture_set: dict, base_dir: Path) -> dict:
    textures = {}
    for item in texture_set.get("textures", []):
        if not item.get("approved", False):
            continue
        path = Path(item.get("path", ""))
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            continue
        texture_id = item.get("texture_id") or item.get("role")
        textures[texture_id] = {**item, "path": str(path.resolve())}
        role = item.get("role")
        if role and role not in textures:
            textures[role] = textures[texture_id]
    return textures


def approved_solids(texture_set: dict) -> dict:
    solids = {}
    for item in texture_set.get("solids", []):
        if item.get("approved", True):
            solids[item.get("solid_id", "solid")] = item
    return solids


def approved_motifs(texture_set: dict, base_dir: Path) -> dict:
    motifs = {}
    for item in texture_set.get("motifs", []):
        if not item.get("approved", False):
            continue
        path = Path(item.get("path", ""))
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            continue
        motif_id = item.get("motif_id") or item.get("role")
        motifs[motif_id] = {**item, "path": str(path.resolve())}
        role = item.get("role")
        if role and role not in motifs:
            motifs[role] = motifs[motif_id]
    return motifs


def tile_image(tile: Image.Image, size: tuple[int, int], offset_x: int = 0, offset_y: int = 0) -> Image.Image:
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    start_x = -tile.width + (offset_x % max(1, tile.width))
    start_y = -tile.height + (offset_y % max(1, tile.height))
    for y in range(start_y, size[1], tile.height):
        for x in range(start_x, size[0], tile.width):
            out.alpha_composite(tile, (x, y))
    return out


def auto_rotation_for_direction(texture: Image.Image, texture_direction: str, piece: dict) -> float:
    if not texture_direction:
        return 0
    piece_aspect = piece.get("width", 1) / max(1, piece.get("height", 1))
    tex_aspect = texture.width / max(1, texture.height)
    if 0.7 <= tex_aspect <= 1.4:
        return 0
    is_tex_horizontal = tex_aspect > 1
    is_piece_horizontal = piece_aspect > 1
    if texture_direction == "longitudinal":
        if is_piece_horizontal != is_tex_horizontal:
            return 90
    elif texture_direction == "transverse":
        if is_piece_horizontal == is_tex_horizontal:
            return 90
    return 0


def transform_texture(texture: Image.Image, plan: dict, piece: dict | None = None) -> Image.Image:
    out = texture.convert("RGBA")
    if plan.get("mirror_x"):
        out = ImageOps.mirror(out)
    if plan.get("mirror_y"):
        out = ImageOps.flip(out)
    scale = max(0.05, float(plan.get("scale", 1) or 1))
    if abs(scale - 1) > 0.001:
        out = out.resize((max(1, round(out.width * scale)), max(1, round(out.height * scale))), Image.Resampling.LANCZOS)
    rotation = float(plan.get("rotation", 0) or 0)
    if piece:
        rotation += auto_rotation_for_direction(out, plan.get("texture_direction", ""), piece)
        piece_orientation = piece.get("pattern_orientation", 0)
        if plan.get("respect_pattern_orientation") and piece_orientation:
            rotation += piece_orientation
    if abs(rotation % 360) > 0.001:
        out = out.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return out


def apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    out = image.convert("RGBA")
    opacity = max(0.0, min(1.0, float(opacity)))
    if opacity >= 0.999:
        return out
    alpha = out.getchannel("A").point(lambda value: round(value * opacity))
    out.putalpha(alpha)
    return out


def apply_mask(content: Image.Image, mask_path: str | Path) -> Image.Image:
    with Image.open(mask_path).convert("L") as mask:
        if content.size != mask.size:
            content = content.resize(mask.size, Image.Resampling.LANCZOS)
        out = content.convert("RGBA")
        out.putalpha(mask)
        return out


def anchor_position(anchor: str, canvas_size: tuple[int, int], item_size: tuple[int, int], offset_x: int, offset_y: int) -> tuple[int, int]:
    width, height = canvas_size
    item_w, item_h = item_size
    positions = {
        "center": ((width - item_w) // 2, (height - item_h) // 2),
        "top": ((width - item_w) // 2, 0),
        "bottom": ((width - item_w) // 2, height - item_h),
        "left": (0, (height - item_h) // 2),
        "right": (width - item_w, (height - item_h) // 2),
        "top_left": (0, 0),
        "top_right": (width - item_w, 0),
        "bottom_left": (0, height - item_h),
        "bottom_right": (width - item_w, height - item_h),
    }
    x, y = positions.get(anchor, positions["center"])
    return x + offset_x, y + offset_y


def compute_motif_visibility(motif: Image.Image, piece_size: tuple[int, int], pos: tuple[int, int], mask_path: str | Path) -> float:
    canvas = Image.new("RGBA", piece_size, (0, 0, 0, 0))
    canvas.alpha_composite(motif, pos)
    alpha = canvas.getchannel("A")
    with Image.open(mask_path).convert("L") as mask:
        if mask.size != piece_size:
            mask = mask.resize(piece_size, Image.Resampling.LANCZOS)
        mask_pixels = list(mask.getdata())
        alpha_pixels = list(alpha.getdata())
        visible = 0
        total = 0
        for mp, ap in zip(mask_pixels, alpha_pixels):
            if ap > 10:
                total += 1
                if mp > 128:
                    visible += 1
    return visible / max(1, total)


def smart_motif_placement(motif: Image.Image, piece: dict, layer: dict) -> tuple[int, int]:
    piece_size = (piece.get("width", 1), piece.get("height", 1))
    mask_path = piece.get("mask_path", "")
    initial_pos = anchor_position(
        layer.get("anchor", "center"),
        piece_size,
        motif.size,
        int(layer.get("offset_x", 0) or 0),
        int(layer.get("offset_y", 0) or 0),
    )
    if not mask_path or not Path(mask_path).exists():
        return initial_pos
    initial_vis = compute_motif_visibility(motif, piece_size, initial_pos, mask_path)
    if initial_vis >= 0.85:
        return initial_pos
    best_pos = initial_pos
    best_vis = initial_vis
    search_range = min(piece.get("width", 1), piece.get("height", 1)) // 5
    step = max(2, search_range // 8)
    for dx in range(-search_range, search_range + 1, step):
        for dy in range(-search_range, search_range + 1, step):
            test_pos = (initial_pos[0] + dx, initial_pos[1] + dy)
            if test_pos[0] + motif.width < 0 or test_pos[0] > piece.get("width", 1):
                continue
            if test_pos[1] + motif.height < 0 or test_pos[1] > piece.get("height", 1):
                continue
            vis = compute_motif_visibility(motif, piece_size, test_pos, mask_path)
            if vis > best_vis:
                best_vis = vis
                best_pos = test_pos
    return best_pos


def render_texture_layer(piece: dict, layer: dict, texture_info: dict) -> Image.Image:
    texture = Image.open(texture_info["path"]).convert("RGBA")
    texture = transform_texture(texture, layer, piece)
    content = tile_image(texture, (piece.get("width", 1), piece.get("height", 1)), int(layer.get("offset_x", 0) or 0), int(layer.get("offset_y", 0) or 0))
    return apply_opacity(content, float(layer.get("opacity", 1) or 1))


def render_solid_layer(piece: dict, layer: dict, solids: dict) -> Image.Image:
    solid = solids.get(layer.get("solid_id")) or next(iter(solids.values()), {"color": "#6f9a4d"})
    try:
        color = ImageColor.getrgb(solid.get("color", "#6f9a4d")) + (255,)
    except Exception:
        color = (107, 143, 69, 255)
    return apply_opacity(Image.new("RGBA", (piece.get("width", 1), piece.get("height", 1)), color), float(layer.get("opacity", 1) or 1))


def render_motif_layer(piece: dict, layer: dict, motif_info: dict) -> Image.Image:
    motif = Image.open(motif_info["path"]).convert("RGBA")
    if layer.get("mirror_x"):
        motif = ImageOps.mirror(motif)
    if layer.get("mirror_y"):
        motif = ImageOps.flip(motif)
    scale = max(0.05, float(layer.get("scale", 1) or 1))
    width_scale = max(0.05, float(layer.get("max_width_scale", scale) or scale))
    height_scale = max(0.05, float(layer.get("max_height_scale", scale) or scale))
    target_max_w = max(1, round(piece.get("width", 1) * width_scale))
    target_max_h = max(1, round(piece.get("height", 1) * height_scale))
    if layer.get("seam_lock"):
        if layer.get("fit_within_piece"):
            ratio = min(target_max_w / max(1, motif.width), target_max_h / max(1, motif.height))
        else:
            ratio = target_max_h / max(1, motif.height)
    else:
        ratio = min(target_max_w / max(1, motif.width), target_max_h / max(1, motif.height))
    motif = motif.resize((max(1, round(motif.width * ratio)), max(1, round(motif.height * ratio))), Image.Resampling.LANCZOS)
    rotation = float(layer.get("rotation", 0) or 0)
    piece_orientation = piece.get("pattern_orientation", 0)
    if piece_orientation:
        rotation += piece_orientation
    if abs(rotation % 360) > 0.001:
        motif = motif.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    content = Image.new("RGBA", (piece.get("width", 1), piece.get("height", 1)), (0, 0, 0, 0))
    if layer.get("seam_lock"):
        pos = anchor_position(layer.get("anchor", "center"), (piece.get("width", 1), piece.get("height", 1)), motif.size, int(layer.get("offset_x", 0) or 0), int(layer.get("offset_y", 0) or 0))
    else:
        pos = smart_motif_placement(motif, piece, layer)
    content.alpha_composite(motif, pos)
    return content


def layer_to_image(piece: dict, layer: dict, textures: dict, solids: dict, motifs: dict) -> Image.Image:
    fill_type = layer.get("fill_type", "texture")
    if fill_type == "solid":
        return render_solid_layer(piece, layer, solids)
    if fill_type == "motif":
        motif_id = layer.get("motif_id")
        motif_info = motifs.get(motif_id)
        if not motif_info:
            raise RuntimeError(f"裁片 {piece.get('piece_id')} 的图案 {motif_id!r} 不可用或缺失。")
        return render_motif_layer(piece, layer, motif_info)
    texture_id = layer.get("texture_id")
    texture_info = textures.get(texture_id)
    if not texture_info:
        raise RuntimeError(f"裁片 {piece.get('piece_id')} 的面料 {texture_id!r} 不可用或缺失。")
    return render_texture_layer(piece, layer, texture_info)


def render_layered_piece(piece: dict, plan: dict, textures: dict, solids: dict, motifs: dict) -> Image.Image:
    layers = [plan.get("base"), plan.get("overlay"), plan.get("trim")]
    layers = [layer for layer in layers if isinstance(layer, dict)]
    if not layers:
        if plan.get("fill_type") == "solid":
            return apply_mask(render_solid_layer(piece, plan, solids), piece["mask_path"])
        texture_id = plan.get("texture_id")
        texture_info = textures.get(texture_id)
        if not texture_info:
            raise RuntimeError(f"裁片 {piece.get('piece_id')} 的面料 {texture_id!r} 不可用或缺失。")
        texture = Image.open(texture_info["path"]).convert("RGBA")
        texture = transform_texture(texture, plan)
        content = tile_image(texture, (piece.get("width", 1), piece.get("height", 1)), int(plan.get("offset_x", 0) or 0), int(plan.get("offset_y", 0) or 0))
        return apply_mask(content, piece["mask_path"])
    content = Image.new("RGBA", (piece.get("width", 1), piece.get("height", 1)), (0, 0, 0, 0))
    for layer in layers:
        layer_image = layer_to_image(piece, layer, textures, solids, motifs)
        content.alpha_composite(layer_image)
    return apply_mask(content, piece["mask_path"])


# ---------------------------------------------------------------------------
# Front pair rendering (cross-seam alignment)
# ---------------------------------------------------------------------------

def _align_image_size(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    if img.width == target_w and img.height == target_h:
        return img
    new = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    x = (target_w - img.width) // 2
    y = (target_h - img.height) // 2
    new.paste(img, (x, y))
    return new


def _mask_image(piece: dict) -> Image.Image:
    return Image.open(piece["mask_path"]).convert("L")


def _front_orientation(piece: dict) -> int:
    try:
        return int(float(piece.get("pattern_orientation", 0) or 0)) % 360
    except Exception:
        return 0


def _normalize_front_image(img: Image.Image, orientation: int) -> Image.Image:
    if orientation == 180:
        return img.rotate(180, expand=False)
    return img


def _restore_front_image(img: Image.Image, orientation: int) -> Image.Image:
    if orientation == 180:
        return img.rotate(180, expand=False)
    return img


def _apply_mask_image(content: Image.Image, mask: Image.Image) -> Image.Image:
    if content.size != mask.size:
        content = content.resize(mask.size, Image.Resampling.LANCZOS)
    out = content.convert("RGBA")
    out.putalpha(mask)
    return out


def _largest_histogram_rect2(heights: list[int], row_bottom: int, seam_x: int | None = None) -> tuple[int, int, int, int, int]:
    best = (0, 0, 0, 0, 0)
    stack: list[int] = []
    for idx in range(len(heights) + 1):
        current = heights[idx] if idx < len(heights) else 0
        while stack and current < heights[stack[-1]]:
            top = stack.pop()
            h = heights[top]
            left = stack[-1] + 1 if stack else 0
            w = idx - left
            if h > 0 and w > 0 and (seam_x is None or left < seam_x < left + w):
                area = w * h
                if area > best[0]:
                    best = (area, left, row_bottom - h + 1, w, h)
        stack.append(idx)
    return best


def _largest_rect_in_binary2(mask: Image.Image, seam_x: int | None = None) -> tuple[int, int, int, int]:
    binary = mask.convert("L").point(lambda value: 255 if value > 128 else 0)
    max_side = 420
    scale = min(1.0, max_side / max(1, max(binary.size)))
    if scale < 1.0:
        resized = binary.resize((max(1, round(binary.width * scale)), max(1, round(binary.height * scale))), Image.Resampling.NEAREST)
        scaled_seam = round(seam_x * scale) if seam_x is not None else None
    else:
        resized = binary
        scaled_seam = seam_x
    pixels = list(resized.getdata())
    heights = [0] * resized.width
    best = (0, 0, 0, 0, 0)
    for y in range(resized.height):
        row = y * resized.width
        for x in range(resized.width):
            heights[x] = heights[x] + 1 if pixels[row + x] > 128 else 0
        current = _largest_histogram_rect2(heights, y, scaled_seam)
        if current[0] > best[0]:
            best = current
    if best[0] <= 0:
        bbox = binary.getbbox()
        return bbox or (0, 0, binary.width, binary.height)
    _, x, y, w, h = best
    if scale < 1.0:
        return (
            max(0, round(x / scale)),
            max(0, round(y / scale)),
            min(mask.width, round((x + w) / scale)),
            min(mask.height, round((y + h) / scale)),
        )
    return (x, y, x + w, y + h)


def _seam_span(mask: Image.Image, side: str) -> tuple[int, int]:
    w, h = mask.size
    depth = max(8, min(64, max(1, w // 6)))
    if side == "right":
        xs = range(max(0, w - depth), w)
    else:
        xs = range(0, min(w, depth))
    pixels = mask.load()
    ys = [y for y in range(h) if any(pixels[x, y] > 128 for x in xs)]
    if ys:
        return min(ys), max(ys) + 1
    bbox = mask.getbbox()
    if bbox:
        return bbox[1], bbox[3]
    return 0, h


def _front_pair_layout(left_piece: dict, right_piece: dict) -> dict:
    left_orientation = _front_orientation(left_piece)
    right_orientation = _front_orientation(right_piece)
    left_raw_mask = _mask_image(left_piece)
    right_raw_mask = _mask_image(right_piece)
    left_mask = _normalize_front_image(left_raw_mask, left_orientation)
    right_mask = _normalize_front_image(right_raw_mask, right_orientation)
    left_span = _seam_span(left_mask, "right")
    right_span = _seam_span(right_mask, "left")
    left_mid = (left_span[0] + left_span[1]) / 2
    right_mid = (right_span[0] + right_span[1]) / 2
    left_y = 0
    right_y = round(left_mid - right_mid)
    min_y = min(left_y, right_y)
    if min_y < 0:
        left_y -= min_y
        right_y -= min_y
    width = left_mask.width + right_mask.width
    height = max(left_y + left_mask.height, right_y + right_mask.height)
    return {
        "left_mask": left_mask,
        "right_mask": right_mask,
        "left_raw_mask": left_raw_mask,
        "right_raw_mask": right_raw_mask,
        "left_orientation": left_orientation,
        "right_orientation": right_orientation,
        "left_xy": (0, left_y),
        "right_xy": (left_mask.width, right_y),
        "size": (width, height),
        "seam_x": left_mask.width,
        "left_span": left_span,
        "right_span": right_span,
    }


def _combined_front_mask(layout: dict) -> Image.Image:
    mask = Image.new("L", layout["size"], 0)
    mask.paste(layout["left_mask"], layout["left_xy"])
    mask.paste(layout["right_mask"], layout["right_xy"])
    return mask


def _front_pair_ids(pieces_payload: dict, entries: dict) -> tuple[str | None, str | None]:
    candidates = [
        pid for pid, plan in entries.items()
        if plan.get("front_pair_seam_locked")
        or (isinstance(plan.get("base"), dict) and plan["base"].get("global_front_texture"))
        or (
            isinstance(plan.get("pair_texture_constraint"), dict)
            and plan["pair_texture_constraint"].get("mode") == "front_seam"
        )
        or (
            isinstance(plan.get("base"), dict)
            and plan["base"].get("pair_texture_constraint") == "front_seam"
        )
        or (isinstance(plan.get("overlay"), dict) and plan["overlay"].get("global_front_motif"))
        or (isinstance(plan.get("overlay"), dict) and plan["overlay"].get("motif_id") in {"theme_front_full", "theme_front_left", "theme_front_right"})
    ]
    piece_by_id = {piece["piece_id"]: piece for piece in pieces_payload.get("pieces", [])}
    candidates = [pid for pid in candidates if pid in piece_by_id]
    if len(candidates) < 2:
        return None, None

    def _side_score(pid: str) -> tuple[int, int, str]:
        plan = entries[pid]
        overlay = plan.get("overlay") if isinstance(plan.get("overlay"), dict) else {}
        text = " ".join(str(value) for value in (overlay.get("motif_id"), overlay.get("legacy_split_motif_id"), plan.get("reason", "")))
        if "theme_front_left" in text or "左前片" in text:
            side = 0
        elif "theme_front_right" in text or "右前片" in text:
            side = 1
        else:
            side = 0
        return side, piece_by_id[pid].get("source_x", 0), pid

    ordered = sorted(candidates[:], key=_side_score)
    if len(ordered) >= 2:
        return ordered[0], ordered[1]
    return None, None


def _load_front_motif(overlay: dict, motifs: dict) -> Image.Image | None:
    motif_id = overlay.get("motif_id")
    if motif_id in {"theme_front_left", "theme_front_right"} and motifs.get("theme_front_full"):
        motif_id = "theme_front_full"
    motif_info = motifs.get(motif_id)
    if motif_info and motif_id not in {"theme_front_left", "theme_front_right"}:
        return Image.open(motif_info["path"]).convert("RGBA")
    left_info = motifs.get("theme_front_left")
    right_info = motifs.get("theme_front_right")
    if not left_info or not right_info:
        return None
    left = Image.open(left_info["path"]).convert("RGBA")
    right = Image.open(right_info["path"]).convert("RGBA")
    height = max(left.height, right.height)
    full = Image.new("RGBA", (left.width + right.width, height), (0, 0, 0, 0))
    full.alpha_composite(left, (0, (height - left.height) // 2))
    full.alpha_composite(right, (left.width, (height - right.height) // 2))
    return full


def _render_front_pair_base(canvas_size: tuple[int, int], base: dict, textures: dict, solids: dict) -> Image.Image:
    if not isinstance(base, dict):
        return Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if base.get("fill_type") == "solid":
        solid = solids.get(base.get("solid_id")) or next(iter(solids.values()), {"color": "#6f9a4d"})
        try:
            color = ImageColor.getrgb(solid.get("color", "#6f9a4d")) + (255,)
        except Exception:
            color = (107, 143, 69, 255)
        return apply_opacity(Image.new("RGBA", canvas_size, color), float(base.get("opacity", 1) or 1))
    texture_id = base.get("texture_id")
    texture_info = textures.get(texture_id)
    if not texture_info:
        raise RuntimeError(f"左右前片连续纹理 {texture_id!r} 不可用或缺失。")
    texture = Image.open(texture_info["path"]).convert("RGBA")
    pseudo_piece = {"width": canvas_size[0], "height": canvas_size[1]}
    texture = transform_texture(texture, base, pseudo_piece)
    return apply_opacity(tile_image(texture, canvas_size, int(base.get("offset_x", 0) or 0), int(base.get("offset_y", 0) or 0)), float(base.get("opacity", 1) or 1))


def _render_front_pair_motif(canvas_size: tuple[int, int], layout: dict, overlay: dict, motifs: dict) -> Image.Image:
    motif = _load_front_motif(overlay, motifs)
    content = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if motif is None:
        return content
    if overlay.get("mirror_x"):
        motif = ImageOps.mirror(motif)
    if overlay.get("mirror_y"):
        motif = ImageOps.flip(motif)
    rotation = float(overlay.get("rotation", 0) or 0)
    if abs(rotation % 360) > 0.001:
        motif = motif.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    combined_mask = _combined_front_mask(layout)
    safe = _largest_rect_in_binary2(combined_mask, seam_x=layout["seam_x"])
    safe_w = max(1, safe[2] - safe[0])
    safe_h = max(1, safe[3] - safe[1])
    multiplier = max(0.05, float(overlay.get("front_pair_scale_multiplier", overlay.get("scale", 0.70)) or 0.70))
    ratio = min(safe_w / max(1, motif.width), safe_h / max(1, motif.height)) * multiplier
    motif = motif.resize((max(1, round(motif.width * ratio)), max(1, round(motif.height * ratio))), Image.Resampling.LANCZOS)
    x = round(safe[0] + (safe_w - motif.width) / 2 + int(overlay.get("offset_x", 0) or 0))
    y = round(safe[1] + (safe_h - motif.height) / 2 + int(overlay.get("offset_y", 0) or 0))
    content.alpha_composite(motif, (x, y))
    return apply_opacity(content, float(overlay.get("opacity", 1) or 1))


def render_front_pair(pieces_payload: dict, entries: dict, textures: dict, solids: dict, motifs: dict, out_dir: Path) -> dict[str, Image.Image]:
    left_id, right_id = _front_pair_ids(pieces_payload, entries)
    if not left_id or not right_id:
        return {}
    piece_by_id = {piece["piece_id"]: piece for piece in pieces_payload.get("pieces", [])}
    left_piece = piece_by_id[left_id]
    right_piece = piece_by_id[right_id]
    left_plan = entries[left_id]
    right_plan = entries[right_id]
    layout = _front_pair_layout(left_piece, right_piece)
    content = _render_front_pair_base(layout["size"], left_plan.get("base") or right_plan.get("base"), textures, solids)
    overlay = left_plan.get("overlay") if isinstance(left_plan.get("overlay"), dict) else right_plan.get("overlay")
    if isinstance(overlay, dict) and overlay.get("fill_type") == "motif":
        content.alpha_composite(_render_front_pair_motif(layout["size"], layout, overlay, motifs))

    combined_mask = _combined_front_mask(layout)
    check = Image.new("RGBA", layout["size"], (255, 255, 255, 255))
    check.alpha_composite(_apply_mask_image(content, combined_mask))
    check.save(out_dir / "front_pair_check.png")

    left_x, left_y = layout["left_xy"]
    right_x, right_y = layout["right_xy"]
    left_crop = content.crop((left_x, left_y, left_x + left_piece["width"], left_y + left_piece["height"]))
    right_crop = content.crop((right_x, right_y, right_x + right_piece["width"], right_y + right_piece["height"]))
    left_crop = _restore_front_image(left_crop, layout["left_orientation"])
    right_crop = _restore_front_image(right_crop, layout["right_orientation"])
    rendered = {
        left_id: _apply_mask_image(left_crop, layout["left_raw_mask"]),
        right_id: _apply_mask_image(right_crop, layout["right_raw_mask"]),
    }
    for pid, piece, plan in ((left_id, left_piece, left_plan), (right_id, right_piece, right_plan)):
        trim = plan.get("trim")
        if isinstance(trim, dict):
            trim_image = layer_to_image(piece, trim, textures, solids, motifs)
            rendered[pid].alpha_composite(_apply_mask_image(trim_image, _mask_image(piece)))
    return rendered


# ---------------------------------------------------------------------------
# Main render entry points
# ---------------------------------------------------------------------------

def render_all(pieces_payload: dict, texture_set: dict, fill_plan: dict, out_dir: Path, texture_set_path: Path | None = None) -> list[dict]:
    textures = approved_textures(texture_set, texture_set_path.parent if texture_set_path else out_dir)
    solids = approved_solids(texture_set)
    motifs = approved_motifs(texture_set, texture_set_path.parent if texture_set_path else out_dir)
    if not textures:
        raise RuntimeError("没有可用面料。请在面料组合.json 中设置 approved=true 后再渲染。")
    entries = {item.get("piece_id"): item for item in fill_plan.get("pieces", [])}
    pieces_dir = out_dir / "pieces"
    pieces_dir.mkdir(parents=True, exist_ok=True)

    slave_map = {}
    for item in fill_plan.get("pieces", []):
        src = item.get("symmetry_source")
        if src:
            slave_map[item["piece_id"]] = {"source": src, "transform": item.get("symmetry_transform", {})}

    rendered_paths = {}
    rendered = []
    front_pair_images = render_front_pair(pieces_payload, entries, textures, solids, motifs, out_dir)
    for piece in pieces_payload.get("pieces", []):
        pid = piece["piece_id"]
        image = front_pair_images.get(pid)
        if image is None:
            continue
        output_path = pieces_dir / f"{pid}.png"
        image.save(output_path)
        rendered_paths[pid] = output_path
        rendered.append({"piece_id": pid, "output_path": str(output_path.resolve()), "plan": entries.get(pid)})

    for piece in pieces_payload.get("pieces", []):
        pid = piece["piece_id"]
        if pid in front_pair_images:
            continue
        if pid in slave_map:
            continue
        plan = entries.get(pid)
        if not plan:
            raise RuntimeError(f"裁片 {pid} 缺少填充计划")
        image = render_layered_piece(piece, plan, textures, solids, motifs)
        output_path = pieces_dir / f"{pid}.png"
        image.save(output_path)
        rendered_paths[pid] = output_path
        rendered.append({"piece_id": pid, "output_path": str(output_path.resolve()), "plan": plan})

    for piece in pieces_payload.get("pieces", []):
        pid = piece["piece_id"]
        if pid not in slave_map:
            continue
        slave_info = slave_map[pid]
        master_path = rendered_paths.get(slave_info["source"])
        if not master_path:
            raise RuntimeError(f"slave 裁片 {pid} 的 master {slave_info['source']} 未渲染")
        with Image.open(master_path).convert("RGBA") as img:
            transform = slave_info["transform"]
            if transform.get("mirror_x"):
                img = ImageOps.mirror(img)
            if transform.get("mirror_y"):
                img = ImageOps.flip(img)
            target_w = piece.get("width", img.width)
            target_h = piece.get("height", img.height)
            if img.width != target_w or img.height != target_h:
                if abs(img.width - target_w) > 5 or abs(img.height - target_h) > 5:
                    plan = entries.get(pid)
                    img = render_layered_piece(piece, plan, textures, solids, motifs)
                else:
                    img = _align_image_size(img, target_w, target_h)
            output_path = pieces_dir / f"{pid}.png"
            img.save(output_path)
            rendered_paths[pid] = output_path
            rendered.append({"piece_id": pid, "output_path": str(output_path.resolve()), "plan": entries.get(pid)})

    return rendered


def compose_preview(pieces_payload: dict, rendered: list[dict], out_path: Path) -> Path:
    canvas = pieces_payload.get("canvas") or {}
    pieces = pieces_payload.get("pieces", [])
    width = int(canvas.get("width") or max(piece["source_x"] + piece["width"] for piece in pieces))
    height = int(canvas.get("height") or max(piece["source_y"] + piece["height"] for piece in pieces))
    preview = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    by_id = {item["piece_id"]: item for item in rendered}
    for piece in pieces:
        item = by_id[piece["piece_id"]]
        with Image.open(item["output_path"]).convert("RGBA") as img:
            preview.alpha_composite(img, (piece["source_x"], piece["source_y"]))
    preview.save(out_path)
    white = Image.new("RGBA", preview.size, (255, 255, 255, 255))
    white.alpha_composite(preview)
    white.convert("RGB").save(out_path.with_name("preview_white.jpg"), quality=95)
    return out_path
