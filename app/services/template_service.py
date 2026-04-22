"""Template loading and resolution."""
import copy
import json
from pathlib import Path

from app.config import settings


GARMENT_TYPE_MAP = {
    "t恤": "DDS26126XCJ01L",
    "t 恤": "DDS26126XCJ01L",
    "t-shirt": "DDS26126XCJ01L",
    "tee": "DDS26126XCJ01L",
    "衬衫": "DDS26126XCJ01L",
    "男士衬衫": "DDS26126XCJ01L",
    "shirt": "DDS26126XCJ01L",
    "防晒服": "BFSK26308XCJ01L",
    "防晒衣": "BFSK26308XCJ01L",
    "sun protection clothing": "BFSK26308XCJ01L",
}


def resolve_template(garment_type: str) -> dict | None:
    """Resolve garment type to template assets."""
    key = garment_type.strip().lower()
    template_id = GARMENT_TYPE_MAP.get(key)
    if not template_id:
        # Try loading index.json for fuzzy match
        index_path = settings.templates_dir / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for tmpl in index.get("templates", []):
                if key in [a.lower() for a in tmpl.get("aliases", [])]:
                    template_id = tmpl["template_id"]
                    break
    if not template_id:
        return None

    size_label = "s"
    tmpl_dir = settings.templates_dir / template_id / size_label
    if not tmpl_dir.exists():
        return None

    pieces_path = tmpl_dir / f"pieces_{size_label}.json"
    garment_map_path = tmpl_dir / f"garment_map_{size_label}.json"

    if not pieces_path.exists() or not garment_map_path.exists():
        return None

    return {
        "template_id": template_id,
        "size_label": size_label,
        "pieces_path": str(pieces_path.resolve()),
        "garment_map_path": str(garment_map_path.resolve()),
        "template_dir": str(tmpl_dir.resolve()),
    }


def load_json(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("False", "false").replace("True", "true")
        return json.loads(text)


def _legacy_texture_direction_to_flow(texture_direction: str) -> str:
    mapping = {
        "longitudinal": "with_piece_upright",
        "transverse": "across_piece_upright",
    }
    return mapping.get(str(texture_direction or "").strip().lower(), "with_piece_upright")


def _texture_flow_to_legacy_direction(texture_flow: str) -> str:
    mapping = {
        "with_piece_upright": "longitudinal",
        "against_piece_upright": "longitudinal",
        "across_piece_upright": "transverse",
    }
    return mapping.get(str(texture_flow or "").strip().lower(), "longitudinal")


def _infer_pair_alignment_mode(piece: dict) -> str:
    garment_role = str(piece.get("garment_role", "") or "")
    symmetry_group = str(piece.get("symmetry_group", "") or "")
    same_shape_group = str(piece.get("same_shape_group", "") or "")
    group_text = f"{garment_role} {symmetry_group} {same_shape_group}"
    if "front" in group_text:
        return "front_seam_continuous"
    if any(token in group_text for token in ("sleeve", "collar")):
        return "identical_shared_phase"
    return "independent"


def _normalize_map_piece(piece: dict) -> tuple[dict, list[dict]]:
    normalized = copy.deepcopy(piece)
    issues: list[dict] = []

    explicit_upright = normalized.get("piece_upright_rotation")
    legacy_upright = normalized.get("pattern_orientation")
    if explicit_upright is not None:
        upright = int(float(explicit_upright or 0)) % 360
        if legacy_upright is not None and int(float(legacy_upright or 0)) % 360 != upright:
            issues.append({
                "type": "template_orientation_conflict",
                "severity": "medium",
                "piece_id": normalized.get("piece_id"),
                "field": "piece_upright_rotation",
                "message": "piece_upright_rotation 与 pattern_orientation 冲突，已优先采用新字段",
            })
    else:
        upright = int(float(legacy_upright or normalized.get("direction_degrees", 0) or 0)) % 360
        if legacy_upright is not None:
            issues.append({
                "type": "template_orientation_migrated",
                "severity": "low",
                "piece_id": normalized.get("piece_id"),
                "field": "piece_upright_rotation",
                "message": "模板仅提供旧方向字段，已兼容推导 piece_upright_rotation",
            })
    normalized["piece_upright_rotation"] = upright
    normalized["pattern_orientation"] = upright
    normalized["direction_degrees"] = upright

    explicit_flow = normalized.get("texture_flow")
    legacy_direction = normalized.get("texture_direction") or normalized.get("texture_direction_hint")
    if explicit_flow:
        texture_flow = str(explicit_flow)
        if legacy_direction:
            inferred_flow = _legacy_texture_direction_to_flow(str(legacy_direction))
            if inferred_flow != texture_flow:
                issues.append({
                    "type": "template_orientation_conflict",
                    "severity": "medium",
                    "piece_id": normalized.get("piece_id"),
                    "field": "texture_flow",
                    "message": "texture_flow 与 texture_direction 冲突，已优先采用新字段",
                })
    else:
        texture_flow = _legacy_texture_direction_to_flow(str(legacy_direction))
        if legacy_direction:
            issues.append({
                "type": "template_orientation_migrated",
                "severity": "low",
                "piece_id": normalized.get("piece_id"),
                "field": "texture_flow",
                "message": "模板仅提供旧纹理方向字段，已兼容推导 texture_flow",
            })
    normalized["texture_flow"] = texture_flow
    legacy_texture_direction = _texture_flow_to_legacy_direction(texture_flow)
    normalized["texture_direction"] = legacy_texture_direction
    normalized["texture_direction_hint"] = legacy_texture_direction

    explicit_pair_alignment = normalized.get("pair_alignment_mode")
    inferred_pair_alignment = _infer_pair_alignment_mode(normalized)
    if explicit_pair_alignment:
        pair_alignment_mode = str(explicit_pair_alignment)
    else:
        pair_alignment_mode = inferred_pair_alignment
    normalized["pair_alignment_mode"] = pair_alignment_mode

    if not normalized.get("orientation_source"):
        normalized["orientation_source"] = "template_defined"

    return normalized, issues


def normalize_template_payloads(pieces_payload: dict, garment_map: dict) -> tuple[dict, dict, list[dict]]:
    """Normalize template orientation fields and mirror them into pieces payload."""
    normalized_pieces = copy.deepcopy(pieces_payload)
    normalized_map = copy.deepcopy(garment_map)
    issues: list[dict] = []

    normalized_map_pieces: list[dict] = []
    piece_meta_by_id: dict[str, dict] = {}
    for piece in normalized_map.get("pieces", []):
        normalized_piece, piece_issues = _normalize_map_piece(piece)
        normalized_map_pieces.append(normalized_piece)
        issues.extend(piece_issues)
        piece_id = normalized_piece.get("piece_id")
        if piece_id:
            piece_meta_by_id[piece_id] = normalized_piece
    normalized_map["pieces"] = normalized_map_pieces
    if issues:
        normalized_map["validation_issues"] = issues

    for piece in normalized_pieces.get("pieces", []):
        meta = piece_meta_by_id.get(piece.get("piece_id"))
        if not meta:
            continue
        for key in (
            "piece_upright_rotation",
            "pattern_orientation",
            "direction_degrees",
            "texture_flow",
            "texture_direction",
            "texture_direction_hint",
            "pair_alignment_mode",
            "orientation_source",
            "garment_role",
            "zone",
            "symmetry_group",
            "same_shape_group",
            "grain_direction",
        ):
            if key in meta:
                piece[key] = meta[key]

    if issues:
        normalized_pieces["validation_issues"] = issues
    return normalized_pieces, normalized_map, issues
