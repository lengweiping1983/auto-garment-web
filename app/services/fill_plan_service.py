"""Piece fill plan service — rule engine for assigning textures to garment pieces.

Ported from scripts/创建填充计划.py — ALL core logic preserved:
- build_rule_plan
- force_theme_front_split_overlays
- apply_symmetry_relations
- enforce_pair_texture_constraints
- enforce_validation
"""
import copy
import json
import math
from pathlib import Path

from PIL import Image


def load_json(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("False", "false").replace("True", "true")
        return json.loads(text)


def approved_ids(texture_set: dict, key: str, id_key: str, fallback_key: str = "role") -> list[str]:
    ids = []
    for item in texture_set.get(key, []):
        if item.get("approved", False):
            value = item.get(id_key) or item.get(fallback_key)
            if value:
                ids.append(value)
    return ids


def choose(ids: list[str], preferred: list[str]) -> str:
    for item in preferred:
        if item in ids:
            return item
    return ids[0] if ids else ""


def make_layer(fill_type: str, reason: str, **kwargs) -> dict:
    layer = {
        "fill_type": fill_type,
        "scale": kwargs.pop("scale", 1.0),
        "rotation": kwargs.pop("rotation", 0),
        "offset_x": kwargs.pop("offset_x", 0),
        "offset_y": kwargs.pop("offset_y", 0),
        "opacity": kwargs.pop("opacity", 1.0),
        "mirror_x": kwargs.pop("mirror_x", False),
        "mirror_y": kwargs.pop("mirror_y", False),
        "reason": reason,
    }
    layer.update({k: v for k, v in kwargs.items() if v not in ("", None)})
    return layer


def find_front_pair_piece_ids(pieces_payload: dict, garment_map: dict) -> tuple[str | None, str | None]:
    gm_entries = garment_map.get("pieces", [])
    left_id = right_id = None
    for item in gm_entries:
        text = " ".join(str(item.get(k, "")) for k in ("piece_name", "reason", "garment_role", "same_shape_group", "symmetry_group"))
        if "前左片" in text or "front_left" in text:
            left_id = item.get("piece_id")
        if "前右片" in text or "front_right" in text:
            right_id = item.get("piece_id")
    if left_id and right_id:
        return left_id, right_id
    piece_by_id = {p["piece_id"]: p for p in pieces_payload.get("pieces", [])}
    front_candidates = [item.get("piece_id") for item in gm_entries if item.get("garment_role") in {"front_body", "front_hero"}]
    front_candidates = [pid for pid in front_candidates if pid in piece_by_id]
    if len(front_candidates) >= 2:
        front_candidates.sort(key=lambda pid: piece_by_id[pid].get("source_x", piece_by_id[pid].get("x", 0)))
        return front_candidates[0], front_candidates[1]
    return None, None


def _largest_histogram_rect(heights: list[int], row_bottom: int, seam_x: int | None = None) -> tuple[int, int, int, int, int]:
    best = (0, 0, 0, 0, 0)
    stack: list[int] = []
    for idx in range(len(heights) + 1):
        current = heights[idx] if idx < len(heights) else 0
        while stack and current < heights[stack[-1]]:
            top = stack.pop()
            h = heights[top]
            left = stack[-1] + 1 if stack else 0
            w = idx - left
            if h > 0 and w > 0:
                crosses_seam = seam_x is None or (left < seam_x < left + w)
                if crosses_seam:
                    area = w * h
                    if area > best[0]:
                        best = (area, left, row_bottom - h + 1, w, h)
        stack.append(idx)
    return best


def _largest_rect_in_binary(mask: Image.Image, seam_x: int | None = None) -> tuple[int, int, int, int]:
    binary = mask.convert("L").point(lambda value: 255 if value > 128 else 0)
    max_side = 420
    scale = min(1.0, max_side / max(1, max(binary.size)))
    if scale < 1.0:
        resized = binary.resize((max(1, round(binary.width * scale)), max(1, round(binary.height * scale))), Image.Resampling.NEAREST)
        scaled_seam = round(seam_x * scale) if seam_x is not None else None
    else:
        resized = binary
        scaled_seam = seam_x
    w, h = resized.size
    pixels = list(resized.getdata())
    heights = [0] * w
    best = (0, 0, 0, 0, 0)
    for y in range(h):
        row = y * w
        for x in range(w):
            heights[x] = heights[x] + 1 if pixels[row + x] > 128 else 0
        current = _largest_histogram_rect(heights, y, scaled_seam)
        if current[0] > best[0]:
            best = current
    if best[0] <= 0:
        return (0, 0, mask.width, mask.height)
    _, x, y, rw, rh = best
    if scale < 1.0:
        return (
            max(0, round(x / scale)),
            max(0, round(y / scale)),
            min(mask.width, round((x + rw) / scale)),
            min(mask.height, round((y + rh) / scale)),
        )
    return (x, y, x + rw, y + rh)


def force_theme_front_split_overlays(
    entries: list[dict],
    pieces_payload: dict,
    texture_set: dict,
    garment_map: dict,
    pieces_base_dir: Path | None = None,
) -> list[dict]:
    """Force generated theme artwork onto the two front pieces when available."""
    theme_front_scale_multiplier = 0.70
    motif_by_id = {m.get("motif_id"): m for m in texture_set.get("motifs", [])}
    motif_ids = set(motif_by_id)
    has_full_front = "theme_front_full" in motif_ids
    has_split_front = {"theme_front_left", "theme_front_right"}.issubset(motif_ids)
    if not has_full_front and not has_split_front:
        return entries
    left_id, right_id = find_front_pair_piece_ids(pieces_payload, garment_map)
    if not left_id or not right_id:
        return entries

    by_id = {e.get("piece_id"): e for e in entries}
    piece_by_id = {p.get("piece_id"): p for p in pieces_payload.get("pieces", [])}
    left_piece = piece_by_id.get(left_id, {})
    right_piece = piece_by_id.get(right_id, {})

    def _resolve_mask_path(piece: dict) -> Path | None:
        value = piece.get("mask_path")
        if not value:
            return None
        path = Path(value)
        if path.is_absolute():
            return path
        if pieces_base_dir:
            return (pieces_base_dir / path).resolve()
        return path.resolve()

    def _front_safe_rect() -> dict:
        left_mask_path = _resolve_mask_path(left_piece)
        right_mask_path = _resolve_mask_path(right_piece)
        if not left_mask_path or not right_mask_path or not left_mask_path.exists() or not right_mask_path.exists():
            lw = max(1, int(left_piece.get("width", 1) or 1))
            lh = max(1, int(left_piece.get("height", 1) or 1))
            rw = max(1, int(right_piece.get("width", 1) or 1))
            rh = max(1, int(right_piece.get("height", 1) or 1))
            return {"x": round(lw * 0.10), "y": round(max(lh, rh) * 0.10), "w": round((lw + rw) * 0.80), "h": round(max(lh, rh) * 0.76), "seam_x": lw}
        left_mask = Image.open(left_mask_path).convert("L")
        right_mask = Image.open(right_mask_path).convert("L")
        if right_mask.height != left_mask.height:
            right_mask = right_mask.resize((right_mask.width, left_mask.height), Image.Resampling.NEAREST)
        combined = Image.new("L", (left_mask.width + right_mask.width, max(left_mask.height, right_mask.height)), 0)
        combined.paste(left_mask, (0, 0))
        combined.paste(right_mask, (left_mask.width, 0))
        seam_x = left_mask.width
        x0, y0, x1, y1 = _largest_rect_in_binary(combined, seam_x=seam_x)
        return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0), "seam_x": seam_x}

    def _motif_size(motif_id: str) -> tuple[int, int]:
        info = motif_by_id.get(motif_id) or {}
        path = info.get("path")
        if not path:
            return 1, 1
        try:
            with Image.open(path) as img:
                return img.size
        except Exception:
            return 1, 1

    def _safe_front_overlay_params(piece: dict, motif_id: str, side_key: str) -> dict:
        motif_w, motif_h = _motif_size(motif_id)
        piece_w = max(1, int(piece.get("width", 1) or 1))
        piece_h = max(1, int(piece.get("height", 1) or 1))
        seam_x = safe_rect["seam_x"]
        rect_left = safe_rect["x"]
        rect_right = safe_rect["x"] + safe_rect["w"]
        if side_key == "left":
            available_w = max(1, seam_x - rect_left)
        else:
            available_w = max(1, rect_right - seam_x)
        safety = 0.965
        max_w = max(0.08, min(0.96, (available_w / piece_w) * safety))
        max_h = max(0.08, min(0.92, (safe_rect["h"] / piece_h) * safety))
        offset_y = round(safe_rect["y"] + safe_rect["h"] / 2 - piece_h / 2)
        return {
            "scale": round(max_h * theme_front_scale_multiplier, 3),
            "max_width_scale": round(max_w * theme_front_scale_multiplier, 3),
            "max_height_scale": round(max_h * theme_front_scale_multiplier, 3),
            "fit_within_piece": True,
            "offset_y": offset_y,
            "safe_rect": safe_rect,
        }

    safe_rect = _front_safe_rect()
    global_motif_id = "theme_front_full" if has_full_front else ""

    for pid, motif_id, side, anchor, seam_lock in (
        (left_id, "theme_front_left", "左前片", "right", "right"),
        (right_id, "theme_front_right", "右前片", "left", "left"),
    ):
        entry = by_id.get(pid)
        if not entry:
            continue
        base = entry.get("base")
        if isinstance(base, dict):
            base["global_front_texture"] = True
            base["front_pair_seam_locked"] = True
        side_key = "left" if motif_id == "theme_front_left" else "right"
        render_motif_id = global_motif_id or motif_id
        sizing_motif_id = motif_id if motif_id in motif_ids else render_motif_id
        sizing = _safe_front_overlay_params(piece_by_id.get(pid, {}), sizing_motif_id, side_key)
        entry["overlay"] = make_layer(
            "motif",
            f"用户主题主体按左右前片连续画布强制落位到{side}，底纹与主图跨中缝对齐",
            motif_id=render_motif_id,
            legacy_split_motif_id=motif_id,
            anchor="center" if global_motif_id else anchor,
            scale=sizing["scale"],
            rotation=0,
            opacity=1.0,
            offset_x=0,
            offset_y=0 if global_motif_id else sizing["offset_y"],
            seam_lock="front_pair" if global_motif_id else seam_lock,
            max_width_scale=sizing["max_width_scale"],
            max_height_scale=sizing["max_height_scale"],
            fit_within_piece=sizing["fit_within_piece"],
            combined_front_safe_rect=sizing["safe_rect"],
            global_front_motif=True,
            front_pair_scale_multiplier=theme_front_scale_multiplier,
        )
        entry["front_pair_seam_locked"] = True
        entry["garment_role"] = "front_body"
        entry["zone"] = "body"
        entry["theme_front_split_forced"] = True
        entry["reason"] = (entry.get("reason", "") + f"；{side}使用程序生成的连续前身主题图").strip("；")
    return entries


def build_rule_plan(pieces_payload: dict, texture_set: dict, garment_map: dict) -> dict:
    """Backend rule engine for fill plan."""
    texture_ids = approved_ids(texture_set, "textures", "texture_id")
    motif_ids = approved_ids(texture_set, "motifs", "motif_id")
    solid_ids = approved_ids(texture_set, "solids", "solid_id")
    if not texture_ids:
        raise RuntimeError("没有可用面料可用于填充计划。")

    main_id = choose(texture_ids, ["main", "base", "secondary", "accent_light", "dark_base"])
    secondary_id = choose(texture_ids, ["secondary", "main", "accent_light", "accent_mid", "dark_base"])
    accent_id = choose(texture_ids, ["accent_light", "accent_mid", "accent", "secondary", "main", "dark_base"])
    dark_id = choose(texture_ids, ["dark_base", "dark", "secondary", "accent_light", "main"])
    trim_solid_id = choose(solid_ids, ["quiet_solid", "quiet_moss", "moss_green", "forest_green", "dark", "solid"])
    motif_id = choose(motif_ids, ["hero_motif", "hero", "accent_motif"])

    by_piece = {item["piece_id"]: item for item in garment_map.get("pieces", [])}
    sorted_pieces = sorted(pieces_payload.get("pieces", []), key=lambda p: p.get("area", 0), reverse=True)
    largest_area = sorted_pieces[0]["area"] if sorted_pieces else 1
    hero_count = 0
    entries = []
    group_params: dict[str, dict] = {}

    for index, piece in enumerate(sorted_pieces):
        map_item = by_piece.get(piece["piece_id"], {})
        role = map_item.get("garment_role", piece.get("piece_role", "unknown"))
        zone = map_item.get("zone", "detail")
        symmetry_group = map_item.get("symmetry_group", "")
        same_shape_group = map_item.get("same_shape_group", "")
        direction = int(map_item.get("direction_degrees", 0) or 0)
        texture_direction = map_item.get("texture_direction", "")
        aspect = piece.get("width", 1) / max(1, piece.get("height", 1))
        area_ratio = piece.get("area", 0) / max(1, largest_area)
        is_true_trim = zone == "trim" or role in ("trim_strip", "collar_or_upper_trim", "hem_or_lower_trim")
        is_trim = is_true_trim and area_ratio < 0.18
        is_hero = role == "front_hero" and hero_count < (1 if len(sorted_pieces) < 8 else 2)
        group_key = same_shape_group or symmetry_group
        if group_key and group_key in group_params:
            params = group_params[group_key]
        else:
            params = {
                "offset_x": 47 * (len(group_params) + index + 1),
                "offset_y": 29 * (len(group_params) + index + 1),
                "scale": None,
            }
            if group_key:
                group_params[group_key] = params
        entry = {
            "piece_id": piece["piece_id"],
            "garment_role": role,
            "zone": zone,
            "symmetry_group": symmetry_group,
            "same_shape_group": same_shape_group,
            "direction_degrees": direction,
            "texture_direction": texture_direction,
            "base": None,
            "overlay": None,
            "trim": None,
            "reason": "",
        }
        if is_trim:
            piece_scale = params.get("scale") or 1.18
            if group_key and params.get("scale") is None:
                params["scale"] = piece_scale
            if dark_id:
                entry["base"] = make_layer("texture", "饰边优先使用深色协调纹理", texture_id=dark_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"])
            elif accent_id:
                entry["base"] = make_layer("texture", "无 dark 纹理时饰边可使用 subtle accent texture", texture_id=accent_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"])
            elif trim_solid_id:
                entry["base"] = make_layer("solid", "仅小型饰边在无纹理可用时使用调色板纯色", solid_id=trim_solid_id)
            entry["reason"] = "饰边使用协调纹理或 subtle accent，保持视觉边界感"
        elif is_hero:
            hero_count += 1
            piece_scale = params.get("scale") or 1.12
            if group_key and params.get("scale") is None:
                params["scale"] = piece_scale
            entry["base"] = make_layer("texture", "前片卖点区使用低噪商业底纹，对齐服装方向", texture_id=main_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"])
            if motif_id:
                entry["overlay"] = make_layer("motif", f"单一卖点图案置于关键可见裁片", motif_id=motif_id, anchor="center", scale=0.72, rotation=0, opacity=1.0, offset_y=-round(piece.get("height", 0) * 0.04))
            entry["reason"] = "前片卖点区承载简化主题，不切割叙事插画"
        elif zone == "body" or role in ("back_body", "secondary_body"):
            piece_scale = params.get("scale") or 1.18
            if group_key and params.get("scale") is None:
                params["scale"] = piece_scale
            entry["base"] = make_layer("texture", "大身裁片使用可穿安静底纹/辅面料，对齐服装方向", texture_id=main_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"])
            entry["reason"] = "大身裁片保持低对比度，确保产品可穿"
        elif zone == "secondary" or role in ("sleeve_pair", "sleeve_or_side_panel"):
            mirror_x = bool(symmetry_group and piece.get("source_x", 0) > (pieces_payload.get("canvas", {}).get("width", 0) / 2))
            piece_scale = params.get("scale") or 1.22
            if group_key and params.get("scale") is None:
                params["scale"] = piece_scale
            entry["base"] = make_layer("texture", "匹配或副面板使用协调纹理，共享组参数", texture_id=secondary_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"], mirror_x=mirror_x)
            entry["reason"] = "副面板增加节奏感，同形裁片保持视觉一致"
        else:
            piece_scale = params.get("scale") or 1.35
            if group_key and params.get("scale") is None:
                params["scale"] = piece_scale
            entry["base"] = make_layer("texture", "小型细节使用受控点缀纹理，不使用复杂叙事艺术", texture_id=accent_id, scale=piece_scale, rotation=0, offset_x=params["offset_x"], offset_y=params["offset_y"])
            entry["reason"] = "小细节支撑色板，避免杂乱"
        entries.append(entry)

    return {
        "plan_id": "commercial_piece_fill_plan_v1",
        "texture_set_id": texture_set.get("texture_set_id", ""),
        "locked": False,
        "pieces": entries,
    }


def apply_symmetry_relations(entries: list[dict], garment_map: dict, pieces_payload: dict | None = None) -> list[dict]:
    gm_pieces = {p["piece_id"]: p for p in garment_map.get("pieces", [])}
    entries_by_id = {e["piece_id"]: e for e in entries}

    def allows_png_symmetry(piece_id: str, rel: dict) -> bool:
        gm = gm_pieces.get(piece_id, {})
        role = gm.get("garment_role", "")
        group = gm.get("symmetry_group") or gm.get("same_shape_group") or ""
        pair_texture_roles = {"front_body", "front_hero", "sleeve_pair", "collar_or_upper_trim"}
        pair_texture_groups = ("front", "sleeve", "collar")
        if rel.get("render_strategy") == "png_mirror" or gm.get("allow_png_symmetry"):
            return True
        if role in pair_texture_roles or any(token in group for token in pair_texture_groups):
            return False
        return True

    slave_map = {}
    for piece_id, gm in gm_pieces.items():
        for rel in gm.get("symmetry_relations", []):
            target_pid = rel.get("target_piece_id")
            if target_pid and target_pid in entries_by_id and allows_png_symmetry(piece_id, rel):
                slave_map[target_pid] = {
                    "source": piece_id,
                    "transform": {"mirror_x": rel.get("mirror_x", False), "mirror_y": rel.get("mirror_y", False)},
                }

    if not slave_map:
        return entries

    new_entries = []
    for entry in entries:
        pid = entry["piece_id"]
        if pid not in slave_map:
            new_entries.append(entry)
            continue
        slave_info = slave_map[pid]
        master_entry = entries_by_id.get(slave_info["source"])
        if not master_entry:
            new_entries.append(entry)
            continue
        slave = copy.deepcopy(master_entry)
        slave["piece_id"] = pid
        slave["symmetry_source"] = slave_info["source"]
        slave["symmetry_transform"] = slave_info["transform"]
        for layer_key in ("base", "overlay", "trim"):
            layer = slave.get(layer_key)
            if layer and isinstance(layer, dict):
                layer["mirror_x"] = False
                layer["mirror_y"] = False
        gm_slave = gm_pieces.get(pid, {})
        for key in ("garment_role", "zone", "symmetry_group", "same_shape_group"):
            if key in gm_slave:
                slave[key] = gm_slave[key]
        new_entries.append(slave)
    return new_entries


def restore_pair_metadata(entries: list[dict], garment_map: dict, issues: list[dict]) -> None:
    gm_by_id = {p.get("piece_id"): p for p in garment_map.get("pieces", [])}
    for entry in entries:
        gm = gm_by_id.get(entry.get("piece_id"))
        if not gm:
            continue
        changed = []
        for key in ("zone", "symmetry_group", "same_shape_group"):
            value = gm.get(key, "")
            if value and entry.get(key) != value:
                entry[key] = value
                changed.append(key)
        if not entry.get("texture_direction") and gm.get("texture_direction"):
            entry["texture_direction"] = gm.get("texture_direction")
            changed.append("texture_direction")
        if entry.get("garment_role") != "front_hero" and gm.get("garment_role") and entry.get("garment_role") != gm.get("garment_role"):
            entry["garment_role"] = gm.get("garment_role")
            changed.append("garment_role")
        if changed:
            issues.append({
                "type": "restored_pair_metadata",
                "severity": "high",
                "piece_id": entry["piece_id"],
                "fields": changed,
                "message": "从 garment_map 恢复左右成对裁片的分组/方向信息",
            })


def _is_pair_texture_piece(item: dict) -> bool:
    role = item.get("garment_role", "")
    group = item.get("symmetry_group") or item.get("same_shape_group") or ""
    return role in {"front_body", "front_hero", "sleeve_pair", "collar_or_upper_trim", "trim_strip"} or any(token in group for token in ("front", "sleeve", "collar", "trim"))


def _pair_group_mode(group: str) -> str:
    if "front" in group:
        return "front_seam"
    if "sleeve" in group:
        return "identical_pair"
    if "collar" in group:
        return "identical_pair"
    return "pair"


def enforce_pair_texture_constraints(entries: list[dict], garment_map: dict, pieces_payload: dict, texture_set: dict, issues: list[dict]) -> None:
    restore_pair_metadata(entries, garment_map, issues)
    by_piece = {p["piece_id"]: p for p in pieces_payload.get("pieces", [])}
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        if entry.get("intentional_asymmetry"):
            continue
        if not _is_pair_texture_piece(entry):
            continue
        group = entry.get("symmetry_group") or entry.get("same_shape_group")
        if not group:
            continue
        groups.setdefault(group, []).append(entry)

    copy_keys = ("fill_type", "texture_id", "solid_id", "scale", "rotation", "mirror_x", "mirror_y", "texture_direction", "respect_pattern_orientation")
    for group, members in groups.items():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda e: (by_piece.get(e["piece_id"], {}).get("source_x", 0), e["piece_id"]))
        master = members[0]
        master_base = master.get("base")
        if not isinstance(master_base, dict):
            continue
        mode = _pair_group_mode(group)
        master_piece = by_piece.get(master["piece_id"], {})
        tex_w, tex_h = 512, 512
        for tex in texture_set.get("textures", []):
            if tex.get("texture_id") != master_base.get("texture_id") and tex.get("role") != master_base.get("texture_id"):
                continue
            path = tex.get("path", "")
            if path and Path(path).exists():
                try:
                    with Image.open(path) as img:
                        tex_w, tex_h = img.size
                except Exception:
                    pass
            break
        scale = max(0.05, float(master_base.get("scale", 1.0) or 1.0))
        tex_w = max(1, round(tex_w * scale))
        tex_h = max(1, round(tex_h * scale))
        rotation = int(float(master_base.get("rotation", 0) or 0)) % 180
        if rotation == 90:
            tex_w, tex_h = tex_h, tex_w
        master_ox = int(master_base.get("offset_x", 0) or 0)
        master_oy = int(master_base.get("offset_y", 0) or 0)

        for member in members:
            base = member.get("base")
            if not isinstance(base, dict):
                member["base"] = dict(master_base)
                base = member["base"]
            changed = []
            for key in copy_keys:
                if key in master_base and base.get(key) != master_base.get(key):
                    base[key] = master_base.get(key)
                    changed.append(key)
            if mode == "front_seam" and member is not master:
                piece = by_piece.get(member["piece_id"], {})
                dx = piece.get("source_x", 0) - master_piece.get("source_x", 0)
                dy = piece.get("source_y", 0) - master_piece.get("source_y", 0)
                new_x = (master_ox - dx) % tex_w
                new_y = (master_oy - dy) % tex_h
            else:
                new_x = master_ox
                new_y = master_oy
            if base.get("offset_x") != round(new_x):
                base["offset_x"] = round(new_x)
                changed.append("offset_x")
            if base.get("offset_y") != round(new_y):
                base["offset_y"] = round(new_y)
                changed.append("offset_y")
            base["pair_texture_constraint"] = mode
            member["pair_texture_constraint"] = {"group": group, "mode": mode, "source_piece_id": master["piece_id"]}
            member.pop("symmetry_source", None)
            member.pop("symmetry_transform", None)
            if changed:
                issues.append({
                    "type": "fixed_pair_texture_constraint",
                    "severity": "high",
                    "piece_id": member["piece_id"],
                    "group": group,
                    "mode": mode,
                    "source_piece_id": master["piece_id"],
                    "fields": sorted(set(changed)),
                    "message": "强制左右成对裁片主纹理一致；前片按缝合相位约束",
                })


def enforce_validation(entries: list[dict], pieces_payload: dict, texture_set: dict, garment_map: dict | None = None) -> tuple[list[dict], list[dict]]:
    issues = []
    by_piece = {p["piece_id"]: p for p in pieces_payload.get("pieces", [])}
    texture_ids = approved_ids(texture_set, "textures", "texture_id")
    solid_ids = approved_ids(texture_set, "solids", "solid_id")
    main_id = choose(texture_ids, ["main", "base", "secondary", "accent_light", "dark_base"])
    garment_map = garment_map or {}
    restore_pair_metadata(entries, garment_map, issues)

    group_templates: dict[str, dict] = {}
    for entry in entries:
        group = entry.get("symmetry_group") or entry.get("same_shape_group")
        if not group:
            continue
        base = entry.get("base")
        if entry.get("intentional_asymmetry"):
            issues.append({"type": "intentional_asymmetry_declared", "severity": "low", "piece_id": entry["piece_id"], "group": group, "message": "裁片声明了有意不对称设计，程序跳过同组一致性强制修正"})
            continue
        if group not in group_templates:
            if isinstance(base, dict):
                group_templates[group] = dict(base)
            continue
        template = group_templates[group]
        if not isinstance(base, dict):
            entry["base"] = dict(template)
            issues.append({"type": "fixed_group_missing_base", "severity": "high", "piece_id": entry["piece_id"], "group": group, "message": "同组成员 base 缺失，已复制 template"})
            continue
        changed = False
        for key in ("fill_type", "texture_id", "solid_id", "scale", "rotation", "offset_x", "offset_y", "mirror_x", "mirror_y", "texture_direction", "respect_pattern_orientation"):
            if base.get(key) != template.get(key):
                base[key] = template[key]
                changed = True
        if changed:
            issues.append({"type": "fixed_group_mismatch", "severity": "high", "piece_id": entry["piece_id"], "group": group, "message": "修正为与同组裁片一致的 base 层参数"})

    hero_entries = [e for e in entries if e.get("garment_role") == "front_hero" or (e.get("overlay") or {}).get("fill_type") == "motif"]
    if len(hero_entries) == 0:
        body_entries = [e for e in entries if e.get("zone") == "body"]
        if body_entries:
            body_entries.sort(key=lambda e: by_piece.get(e["piece_id"], {}).get("area", 0), reverse=True)
            body_entries[0]["garment_role"] = "front_hero"
            if not body_entries[0].get("overlay") and solid_ids:
                body_entries[0]["overlay"] = make_layer("motif", "程序兜底：将最大 body 裁片设为 hero 并添加 motif", motif_id="hero_motif", anchor="center", scale=0.65, rotation=0, opacity=1.0)
            issues.append({"type": "fixed_missing_hero", "severity": "medium", "piece_id": body_entries[0]["piece_id"], "message": "没有 hero 裁片，将最大 body 裁片设为 front_hero"})

    if len(hero_entries) > 2:
        hero_entries.sort(key=lambda e: by_piece.get(e["piece_id"], {}).get("area", 0), reverse=True)
        for extra in hero_entries[2:]:
            extra["garment_role"] = "front_body"
            extra.pop("overlay", None)
            issues.append({"type": "fixed_too_many_heroes", "severity": "medium", "piece_id": extra["piece_id"], "message": "Hero 裁片超过 2 个，多余裁片降级为 front_body 并移除 overlay"})

    for entry in entries:
        pid = entry["piece_id"]
        piece = by_piece.get(pid, {})
        if entry.get("garment_role") == "front_hero":
            overlay = entry.get("overlay")
            if not overlay or overlay.get("fill_type") != "motif":
                entry["overlay"] = make_layer("motif", "Hero 裁片必须有 motif overlay", motif_id="hero_motif", anchor="center", scale=0.65, rotation=0, opacity=1.0)
                issues.append({"type": "fixed_missing_hero_overlay", "severity": "high", "piece_id": pid, "message": "Hero 裁片缺少 motif overlay，已添加"})

    texture_ids_set = set(texture_ids)
    for entry in entries:
        base = entry.get("base")
        if not isinstance(base, dict):
            continue
        if base.get("fill_type") == "texture" and base.get("texture_id") not in texture_ids_set:
            old_id = base.get("texture_id")
            base["texture_id"] = main_id
            issues.append({"type": "fixed_invalid_texture", "severity": "high", "piece_id": entry["piece_id"], "old_texture_id": old_id, "new_texture_id": main_id, "message": f"texture_id {old_id} 不存在，已替换为 main"})

    enforce_pair_texture_constraints(entries, garment_map, pieces_payload, texture_set, issues)
    return entries, issues


def build_fill_plan(
    pieces_payload: dict,
    texture_set: dict,
    garment_map: dict,
    visual_elements: dict | None = None,
) -> dict:
    """Build and validate the complete fill plan."""
    plan = build_rule_plan(pieces_payload, texture_set, garment_map)
    entries = apply_symmetry_relations(plan.get("pieces", []), garment_map, pieces_payload)
    entries = force_theme_front_split_overlays(entries, pieces_payload, texture_set, garment_map, pieces_base_dir=Path(texture_set.get("_base_dir", ".")))
    entries, issues = enforce_validation(entries, pieces_payload, texture_set, garment_map)
    plan["pieces"] = entries
    plan["validation_issues"] = issues
    return plan
