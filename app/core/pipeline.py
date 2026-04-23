"""End-to-end garment production pipeline.

This replaces the CLI script `scripts/端到端自动化.py`.
It uses FastAPI BackgroundTasks (no Redis/Celery for now) and
runs the FULL preserved pipeline:
  Phase 1: Visual analysis (single LLM call)
  Phase 2: Prompt generation (Python rule engine)
  Phase 3: AI asset generation (hero + 3 textures, parallel)
  Phase 4: Front split assets
  Phase 5: Fill plan
  Phase 6: Render variants
"""
import asyncio
import copy
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings
from app.core.neo_ai_client import NeoAIClient
from app.core.prompt_sanitizer import normalize_image_generation_prompt

from PIL import Image, ImageStat
from app.core.renderer import render_all, compose_preview
from app.core.image_utils import generate_thumbnail, _thumb_size_for_role
from app.services.front_split_service import create_front_split_assets, inject_front_split_motifs
from app.services.fill_plan_service import build_fill_plan
from app.services.prompt_engine import generate_texture_prompts, save_texture_prompts
from app.services.hero_prompt_strategy_base import validate_hero_prompt_scheme
from app.services.template_service import resolve_template, normalize_template_payloads
from app.services.vision_service import VisionService


# ---------------------------------------------------------------------------
# Task status persistence (file-based, no Redis)
# ---------------------------------------------------------------------------

def _status_path(task_id: str) -> Path:
    return settings.storage_base_dir / task_id / "status.json"


def _dirty_assets_path(task_id: str) -> Path:
    return settings.storage_base_dir / task_id / "dirty_assets.json"


def _write_status(task_id: str, status: str, progress: dict | None = None, error: str | None = None, user_prompt: str | None = None):
    path = _status_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing_progress = existing.get("progress") or {}
    new_progress = progress or {}

    def _merge_detail(old: dict, new: dict) -> dict:
        result = {}
        for key in set(old.keys()) | set(new.keys()):
            if key in new and key in old:
                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    result[key] = {**old[key], **new[key]}
                else:
                    result[key] = new[key]
            elif key in new:
                result[key] = new[key]
            else:
                result[key] = old[key]
        return result

    merged_progress = {**existing_progress, **new_progress}
    if "detail" in existing_progress and "detail" in new_progress:
        merged_progress["detail"] = _merge_detail(existing_progress["detail"], new_progress["detail"])
    payload = {
        "task_id": task_id,
        "status": status,
        "progress": merged_progress,
        "error": error,
        "updated_at": datetime.now().isoformat(),
    }
    if user_prompt is not None:
        payload["user_prompt"] = user_prompt
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_detail_field(task_id: str, key: str, value: dict):
    """Update a single field in progress.detail without changing overall status."""
    path = _status_path(task_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    progress = data.get("progress") or {}
    detail = progress.get("detail") or {}
    detail[key] = value
    progress["detail"] = detail
    data["progress"] = progress
    data["task_id"] = task_id
    data["updated_at"] = datetime.now().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_detail_patch(task_id: str, detail_patch: dict) -> dict:
    """Merge a partial patch into progress.detail without changing task status."""
    path = _status_path(task_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    progress = data.get("progress") or {}
    detail = progress.get("detail") or {}
    for key, value in detail_patch.items():
        if isinstance(detail.get(key), dict) and isinstance(value, dict):
            detail[key] = {**detail[key], **value}
        else:
            detail[key] = value
    progress["detail"] = detail
    data["progress"] = progress
    data["task_id"] = task_id
    data["updated_at"] = datetime.now().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _set_rerender_state(
    task_id: str,
    status: str,
    *,
    texture_ids: list[str] | None = None,
    hero_changed: bool | None = None,
    current_step: str | None = None,
) -> dict:
    """Track rerender progress in detail without mutating the main task status."""
    detail_patch: dict = {
        "rerender_status": status,
    }
    if current_step is not None:
        detail_patch["rerender_current_step"] = current_step
    scope_patch = {}
    if texture_ids is not None:
        scope_patch["texture_ids"] = texture_ids
    if hero_changed is not None:
        scope_patch["hero_changed"] = hero_changed
    if scope_patch:
        detail_patch["rerender_scope"] = scope_patch
    return _merge_detail_patch(task_id, detail_patch)


def read_task_status(task_id: str) -> dict:
    path = _status_path(task_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if _heal_stale_rerender_state(path, data):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return data
    return {"task_id": task_id, "status": "unknown", "error": "Task not found"}


def _heal_stale_rerender_state(status_path: Path, data: dict) -> bool:
    """Recover tasks whose rerender state stayed on running after work stopped."""
    if data.get("status") != "completed":
        return False
    progress = data.get("progress") or {}
    detail = progress.get("detail") or {}
    if detail.get("rerender_status") != "running":
        return False

    rerender_scope = detail.get("rerender_scope") or {}
    target_texture_ids = [
        tid for tid in rerender_scope.get("texture_ids", [])
        if isinstance(tid, str) and tid
    ]

    updated_at_raw = data.get("updated_at")
    is_old_enough = False
    if updated_at_raw:
        try:
            updated_at = datetime.fromisoformat(updated_at_raw)
            is_old_enough = datetime.now() - updated_at >= timedelta(minutes=2)
        except ValueError:
            pass

    task_dir = status_path.parent
    summary_path = task_dir / "automation_summary.json"
    if not summary_path.exists():
        return False

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    preview_path = summary.get("预览图", "")
    has_preview = bool(preview_path and Path(preview_path).exists())
    variant_summaries = summary.get("裁片模板变体") or []
    rendered_variant_ids = {
        str(item.get("纹理ID"))
        for item in variant_summaries
        if item.get("纹理ID") and Path(item.get("预览图", "")).exists()
    }
    has_variant_outputs = bool(rendered_variant_ids)
    target_outputs_ready = bool(target_texture_ids) and all(tid in rendered_variant_ids for tid in target_texture_ids)
    if not (has_preview or has_variant_outputs):
        return False
    if not (is_old_enough or target_outputs_ready):
        return False

    detail["rerender_status"] = "completed"
    detail["rerender_current_step"] = "completed"
    progress["detail"] = detail
    progress["current_step"] = progress.get("current_step") or "completed"
    data["progress"] = progress
    data["updated_at"] = datetime.now().isoformat()
    status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _normalized_generation_prompt(prompt: str, strict: bool = False) -> str:
    return normalize_image_generation_prompt(prompt, strict=strict)


def clear_rerender_outputs(task_id: str) -> None:
    work_dir = settings.storage_base_dir / task_id
    variants_dir = work_dir / "variants"
    if variants_dir.exists():
        shutil.rmtree(variants_dir)

    for filename in ("automation_summary.json", "piece_fill_plan.json", "texture_set.json"):
        path = work_dir / filename
        if path.exists():
            path.unlink()


def clear_front_split_assets(task_id: str) -> None:
    work_dir = settings.storage_base_dir / task_id
    assets_dir = work_dir / "assets"
    if not assets_dir.exists():
        return
    for filename in ("theme_front_full.png", "theme_front_left.png", "theme_front_right.png"):
        path = assets_dir / filename
        if path.exists():
            path.unlink()


def read_dirty_assets(task_id: str) -> dict:
    path = _dirty_assets_path(task_id)
    if not path.exists():
        return {"hero": False, "textures": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"hero": False, "textures": []}
    textures = [tid for tid in data.get("textures", []) if tid in {"texture_1", "texture_2", "texture_3"}]
    return {"hero": bool(data.get("hero")), "textures": sorted(set(textures))}


def mark_dirty_assets(task_id: str, *, hero: bool = False, textures: list[str] | None = None) -> dict:
    data = read_dirty_assets(task_id)
    if hero:
        data["hero"] = True
    if textures:
        allowed = {"texture_1", "texture_2", "texture_3"}
        data["textures"] = sorted(set(data.get("textures", [])) | {tid for tid in textures if tid in allowed})
    _write_json(_dirty_assets_path(task_id), data)
    return data


def clear_dirty_assets(task_id: str, *, all_assets: bool = False, hero: bool = False, textures: list[str] | None = None) -> dict:
    if all_assets:
        data = {"hero": False, "textures": []}
        _write_json(_dirty_assets_path(task_id), data)
        return data

    data = read_dirty_assets(task_id)
    if hero:
        data["hero"] = False
    if textures:
        remove_set = set(textures)
        data["textures"] = [tid for tid in data.get("textures", []) if tid not in remove_set]
    _write_json(_dirty_assets_path(task_id), data)
    return data


def _build_texture_set(
    out_dir: Path,
    texture_paths: dict[str, Path],
    hero_motif_path: Path | None,
    prompt_map: dict[str, str],
) -> Path:
    """Build root texture_set.json from generated assets."""
    ordered_ids = ["texture_1", "texture_2", "texture_3"]
    available = [tid for tid in ordered_ids if texture_paths.get(tid)]
    if not available:
        raise RuntimeError("没有可写入 texture_set.json 的单纹理资产。")

    textures = []
    for texture_id in available:
        path = texture_paths.get(texture_id)
        textures.append({
            "texture_id": texture_id,
            "path": str(path.resolve()),
            "role": texture_id,
            "approved": True,
            "candidate": False,
            "prompt": prompt_map.get(texture_id, f"Neo AI 单纹理生成：{texture_id}"),
            "model": "neo-ai",
            "seed": "",
        })

    texture_set = {
        "texture_set_id": f"{out_dir.name}_neo_ai_single_texture_set",
        "locked": False,
        "source_mode": "single_textures",
        "partial_success": False,
        "missing_textures": [tid for tid in ordered_ids if tid not in available],
        "textures": textures,
        "motifs": [],
        "solids": [],
    }
    path = out_dir / "texture_set.json"
    _write_json(path, texture_set)
    return path


def _force_fill_plan_to_single_texture(fill_plan: dict, texture_id: str) -> dict:
    """Return a copy where every rendered layer uses one texture."""
    plan = copy.deepcopy(fill_plan)
    plan["plan_id"] = f"{plan.get('plan_id', 'piece_fill_plan')}_{texture_id}_single_texture"
    plan["variant_texture_id"] = texture_id

    def _texture_layer(reason: str = "单纹理模板预览统一使用同一张图案纹理") -> dict:
        return {
            "fill_type": "texture",
            "texture_id": texture_id,
            "scale": 1.0,
            "rotation": 0,
            "offset_x": 0,
            "offset_y": 0,
            "mirror_x": False,
            "mirror_y": False,
            "reason": reason,
        }

    def _force_render_layer(layer):
        if isinstance(layer, dict):
            fill_type = layer.get("fill_type")
            if fill_type == "motif":
                if layer.get("motif_id") in {"theme_front_full", "theme_front_left", "theme_front_right"}:
                    return layer
                return None
            if fill_type in {"texture", "solid"} or "texture_id" in layer or "solid_id" in layer:
                layer["fill_type"] = "texture"
                layer["texture_id"] = texture_id
                layer.pop("solid_id", None)
            for key, value in list(layer.items()):
                forced = _force_render_layer(value)
                if forced is None and isinstance(value, dict):
                    layer.pop(key, None)
                elif forced is not value:
                    layer[key] = forced
            return layer
        elif isinstance(layer, list):
            kept = []
            for item in layer:
                forced = _force_render_layer(item)
                if forced is not None:
                    kept.append(forced)
            return kept
        return layer

    for piece in plan.get("pieces", []):
        piece_motif_id = piece.get("motif_id") if piece.get("fill_type") == "motif" else None
        is_theme_split = piece_motif_id in {"theme_front_full", "theme_front_left", "theme_front_right"}
        preserve_front_pair = bool(
            piece.get("front_pair_seam_locked")
            or (
                isinstance(piece.get("pair_texture_constraint"), dict)
                and piece["pair_texture_constraint"].get("mode") == "front_seam"
            )
            or (
                isinstance(piece.get("base"), dict)
                and (
                    piece["base"].get("front_pair_seam_locked")
                    or piece["base"].get("global_front_texture")
                    or piece["base"].get("pair_texture_constraint") == "front_seam"
                )
            )
        )
        if piece.get("fill_type") == "motif" and not is_theme_split:
            piece.update(_texture_layer("单纹理模板预览移除定位主图，统一使用当前图案纹理"))
        elif piece.get("fill_type") in {"texture", "solid"} or "texture_id" in piece or "solid_id" in piece:
            piece["fill_type"] = "texture"
            piece["texture_id"] = texture_id
            piece.pop("solid_id", None)
        if not any(isinstance(piece.get(key), dict) for key in ("base", "overlay", "trim")) and not is_theme_split:
            piece["fill_type"] = "texture"
            piece["texture_id"] = texture_id
            piece.pop("solid_id", None)
        for key in ("base", "trim"):
            if isinstance(piece.get(key), dict):
                forced = _force_render_layer(piece[key])
                if forced is None:
                    if key == "base":
                        piece[key] = _texture_layer()
                    else:
                        piece.pop(key, None)
                else:
                    piece[key] = forced
        if preserve_front_pair:
            piece["front_pair_seam_locked"] = True
            base = piece.get("base")
            if isinstance(base, dict):
                base["front_pair_seam_locked"] = True
                base["global_front_texture"] = True
                base.setdefault("pair_texture_constraint", "front_seam")
        overlay = piece.get("overlay")
        if isinstance(overlay, dict):
            forced_overlay = _force_render_layer(overlay)
            if forced_overlay is None:
                piece.pop("overlay", None)
            else:
                piece["overlay"] = forced_overlay
        piece["variant_texture_id"] = texture_id
        piece["single_texture_preview_only"] = True
    return plan


# ---------------------------------------------------------------------------
# Stream variant helpers
# ---------------------------------------------------------------------------

def _resume_variant_rendered(work_dir: Path, texture_id: str) -> bool:
    preview = work_dir / "variants" / texture_id / "preview.png"
    return preview.exists()


def _detect_total_memory_bytes() -> int | None:
    """Best-effort detection of total system memory."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
            return pages * page_size
    except (AttributeError, OSError, ValueError):
        pass

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
        except Exception:
            pass
    return None


def _resolve_render_mode() -> tuple[str, dict]:
    """Resolve render mode from config and host memory."""
    configured = (settings.render_mode or "auto").strip().lower()
    valid_modes = {"auto", "stream", "serial"}
    if configured not in valid_modes:
        configured = "auto"

    total_bytes = _detect_total_memory_bytes()
    total_gb = round(total_bytes / (1024 ** 3), 2) if total_bytes else None
    threshold_gb = settings.low_memory_serial_render_threshold_gb

    if configured == "serial":
        mode = "serial"
        reason = "configured_serial"
    elif configured == "stream":
        mode = "stream"
        reason = "configured_stream"
    elif total_bytes is not None and total_bytes <= threshold_gb * (1024 ** 3):
        mode = "serial"
        reason = "low_memory_auto_downgrade"
    else:
        mode = "stream"
        reason = "auto_default"

    return mode, {
        "configured_mode": configured,
        "resolved_mode": mode,
        "reason": reason,
        "total_memory_gb": total_gb,
        "serial_threshold_gb": threshold_gb,
    }


async def _upload_reference_image(
    neo: NeoAIClient, theme_path: Path, work_dir: Path, task_id: str, skip_status: bool = False
) -> str:
    """Upload theme image to Neo AI OSS and return public URL."""
    ref_url_path = work_dir / "reference_image_url.txt"
    if ref_url_path.exists():
        ref_url = ref_url_path.read_text(encoding="utf-8").strip()
        print(f"[UPLOAD] Reference image already uploaded for {task_id}: {ref_url}")
        try:
            _update_detail_field(task_id, "reference_image", {"status": "completed", "url": ref_url})
        except Exception as e:
            print(f"[WARN] Failed to update reference_image status (already uploaded): {e}")
        return ref_url

    if not skip_status:
        _write_status(task_id, "generating", {
            "phase": "neo_ai_generation",
            "completed_steps": ["vision_analysis", "prompt_generation"],
            "current_step": "uploading_reference_image",
        })
    print(f"[UPLOAD] Starting reference image upload for {task_id}")
    try:
        _update_detail_field(task_id, "reference_image", {"status": "uploading"})
    except Exception as e:
        print(f"[WARN] Failed to set reference_image status to uploading: {e}")

    ref_url = await neo.upload_to_oss(theme_path)
    ref_url_path.write_text(ref_url, encoding="utf-8")
    print(f"[UPLOAD] Reference image upload completed for {task_id}: {ref_url}")
    try:
        _update_detail_field(task_id, "reference_image", {"status": "completed", "url": ref_url})
    except Exception as e:
        print(f"[WARN] Failed to set reference_image status to completed: {e}")
    return ref_url


async def _gen_hero(
    neo: NeoAIClient,
    prompt: str,
    ref_url: str,
    model: str,
    size: str,
    hero_dir: Path,
    task_id: str,
) -> Path | Exception:
    """Generate hero motif. Uses LLM prompt directly — no wrapping."""
    _write_status(task_id, "generating", {
        "phase": "neo_ai_generation",
        "completed_steps": ["vision_analysis", "prompt_generation"],
        "current_step": "generating_hero",
    })
    _update_detail_field(task_id, "hero_motif", {"status": "running"})
    try:
        safe_prompt = _normalized_generation_prompt(prompt, strict=False)
        try:
            task_code = await neo.submit_generation(
                prompt=safe_prompt,
                model=model,
                size=size,
                reference_images=[ref_url] if ref_url else None,
            )
        except Exception as exc:
            if not _is_prompt_safety_error(exc):
                raise
            print("[RETRY] Hero prompt hit moderation, retrying with stricter sanitization...")
            safe_prompt = _normalized_generation_prompt(prompt, strict=True)
            task_code = await neo.submit_generation(
                prompt=safe_prompt,
                model=model,
                size=size,
                reference_images=[ref_url] if ref_url else None,
            )
        return await neo.poll_until_complete(task_code, hero_dir)
    except Exception as exc:
        return exc


async def _gen_texture(
    neo: NeoAIClient,
    tid: str,
    prompt: str,
    ref_url: str,
    model: str,
    size: str,
    texture_root: Path,
    task_id: str,
) -> Path | Exception:
    """Generate single texture. Uses LLM prompt directly — no wrapping."""
    _write_status(task_id, "generating", {
        "phase": "neo_ai_generation",
        "completed_steps": ["vision_analysis", "prompt_generation"],
        "current_step": f"generating_texture_{tid}",
    })
    _update_detail_field(task_id, tid, {"status": "running"})
    work = texture_root / tid
    work.mkdir(parents=True, exist_ok=True)
    try:
        safe_prompt = _normalized_generation_prompt(prompt, strict=False)
        try:
            task_code = await neo.submit_generation(
                prompt=safe_prompt,
                model=model,
                size=size,
                reference_images=[ref_url] if ref_url else None,
            )
        except Exception as exc:
            if not _is_prompt_safety_error(exc):
                raise
            print(f"[RETRY] Texture {tid} prompt hit moderation, retrying with stricter sanitization...")
            safe_prompt = _normalized_generation_prompt(prompt, strict=True)
            task_code = await neo.submit_generation(
                prompt=safe_prompt,
                model=model,
                size=size,
                reference_images=[ref_url] if ref_url else None,
            )
        p = await neo.poll_until_complete(task_code, work)
        dest = texture_root / f"{tid}.png"
        shutil.copy2(p, dest)
        return dest
    except Exception as exc:
        return exc


def _is_prompt_safety_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "敏感词",
        "敏感",
        "内容安全",
        "审核",
        "违规",
        "违禁",
        "unsafe",
        "sensitive",
        "inappropriate",
        "content safety",
        "moderation",
        "nsfw",
    )
    return any(marker in text for marker in markers)


async def _generate_variant_thumbnails(variant_dir: Path, task_dir: Path):
    """Generate thumbnails for all images inside a variant directory."""
    try:
        for img_path in variant_dir.iterdir():
            if not img_path.is_file():
                continue
            if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                role = "preview" if "preview" in img_path.name else "front_pair_check"
                await asyncio.to_thread(generate_thumbnail, img_path, task_dir / "thumbnails" / img_path.relative_to(task_dir), _thumb_size_for_role(role))
        pieces_dir = variant_dir / "pieces"
        if pieces_dir.exists():
            for img_path in pieces_dir.iterdir():
                if img_path.is_file() and img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    await asyncio.to_thread(generate_thumbnail, img_path, task_dir / "thumbnails" / img_path.relative_to(task_dir), _thumb_size_for_role("piece"))
    except Exception as e:
        print(f"[WARN] Variant thumbnail generation failed: {e}")


async def _process_variant_when_ready(
    tid: str,
    texture_paths: dict[str, Path],
    hero_path: Path | None,
    front_split_assets: dict | None,
    prompt_map: dict[str, str],
    pieces_payload: dict,
    garment_map: dict,
    visual: dict,
    work_dir: Path,
    task_id: str,
):
    """Render a single variant as soon as hero + texture are ready."""
    if _resume_variant_rendered(work_dir, tid):
        print(f"[RESUME] Variant {tid} already rendered, skipping.")
        return

    _write_status(task_id, "rendering", {
        "phase": "rendering",
        "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan"],
        "current_step": f"rendering_variant_{tid}",
        "detail": {
            "reference_image": {"status": "completed"},
            "hero_motif": {"status": "completed" if hero_path else "failed", "path": str(hero_path) if hero_path else ""},
            "texture_1": {"status": "completed" if "texture_1" in texture_paths else "failed", "path": str(texture_paths.get("texture_1", ""))},
            "texture_2": {"status": "completed" if "texture_2" in texture_paths else "failed", "path": str(texture_paths.get("texture_2", ""))},
            "texture_3": {"status": "completed" if "texture_3" in texture_paths else "failed", "path": str(texture_paths.get("texture_3", ""))},
            "variants": {tid: "rendering"},
        },
    })

    variant_dir = work_dir / "variants" / tid
    variant_dir.mkdir(parents=True, exist_ok=True)

    # Build texture_set with currently available textures
    texture_set_path = await asyncio.to_thread(
        _build_texture_set, work_dir, texture_paths, hero_path, prompt_map
    )
    if front_split_assets:
        inject_front_split_motifs(texture_set_path, front_split_assets)

    texture_set = json.loads(texture_set_path.read_text(encoding="utf-8"))
    texture_set["_base_dir"] = str(work_dir.resolve())

    fill_plan = await asyncio.to_thread(
        build_fill_plan, pieces_payload, texture_set, garment_map, visual
    )
    fill_plan_path = work_dir / "piece_fill_plan.json"
    _write_json(fill_plan_path, fill_plan)

    # Render single-texture variant
    variant_set = copy.deepcopy(texture_set)
    variant_set["texture_set_id"] = f"{texture_set.get('texture_set_id', 'texture_set')}_{tid}_single_texture"
    variant_set["variant_texture_id"] = tid
    variant_set["textures"] = [copy.deepcopy(t) for t in variant_set["textures"] if t.get("texture_id") == tid]
    for item in variant_set["textures"]:
        item["approved"] = True
        item["candidate"] = False
        item["role"] = item.get("role") or tid
    theme_motifs = [copy.deepcopy(m) for m in texture_set.get("motifs", []) if m.get("motif_id") in {"theme_front_full", "theme_front_left", "theme_front_right"}]
    variant_set["motifs"] = theme_motifs
    if texture_set.get("theme_front_split"):
        variant_set["theme_front_split"] = copy.deepcopy(texture_set["theme_front_split"])
    variant_texture_set_path = variant_dir / "texture_set.json"
    _write_json(variant_texture_set_path, variant_set)

    variant_fill_plan = _force_fill_plan_to_single_texture(fill_plan, tid)
    variant_fill_plan_path = variant_dir / "piece_fill_plan.json"
    _write_json(variant_fill_plan_path, variant_fill_plan)

    rendered = await asyncio.to_thread(render_all, pieces_payload, variant_set, variant_fill_plan, variant_dir, variant_texture_set_path)
    await asyncio.to_thread(compose_preview, pieces_payload, rendered, variant_dir / "preview.png")
    await _generate_variant_thumbnails(variant_dir, work_dir)

    _write_status(task_id, "rendering", {
        "phase": "rendering",
        "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan"],
        "current_step": f"rendering_variant_{tid}",
        "detail": {
            "reference_image": {"status": "completed"},
            "hero_motif": {"status": "completed" if hero_path else "failed", "path": str(hero_path) if hero_path else ""},
            "texture_1": {"status": "completed" if "texture_1" in texture_paths else "failed", "path": str(texture_paths.get("texture_1", ""))},
            "texture_2": {"status": "completed" if "texture_2" in texture_paths else "failed", "path": str(texture_paths.get("texture_2", ""))},
            "texture_3": {"status": "completed" if "texture_3" in texture_paths else "failed", "path": str(texture_paths.get("texture_3", ""))},
            "variants": {tid: "completed"},
        },
    })


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Main pipeline with resume support
# ---------------------------------------------------------------------------

async def run_pipeline(
    task_id: str,
    theme_image_path: Path,
    garment_type: str,
    user_prompt: str = "",
    neo_model: str = "",
    neo_size: str = "",
    hero_prompt_scheme: str = "b",
    force_render: bool = False,
    force_render_texture_ids: list[str] | None = None,
    allow_missing_hero: bool = False,
):
    """Run the complete garment production pipeline with resume support and streaming variants."""
    hero_prompt_scheme = validate_hero_prompt_scheme(hero_prompt_scheme)
    work_dir = settings.storage_base_dir / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    render_mode, render_runtime = _resolve_render_mode()
    serial_rendering = render_mode == "serial"
    original_status = read_task_status(task_id).get("status", "unknown")
    preserve_main_status = force_render and original_status == "completed"

    try:
        def _write_pipeline_status(status: str, progress: dict | None = None, error: str | None = None):
            if preserve_main_status:
                rerender_state = "failed" if status == "failed" else ("completed" if status == "completed" else "running")
                current_step = (progress or {}).get("current_step")
                _set_rerender_state(task_id, rerender_state, current_step=current_step)
                if progress and progress.get("detail"):
                    _merge_detail_patch(task_id, progress.get("detail") or {})
                if error is not None:
                    _write_status(task_id, original_status, error=error)
                return
            _write_status(task_id, status, progress=progress, error=error, user_prompt=user_prompt if status == "pending" else None)

        if preserve_main_status:
            _set_rerender_state(task_id, "running", current_step="rerender_setup")
        else:
            _write_status(task_id, "pending", user_prompt=user_prompt)

        # Phase 0: Template resolution (always run, lightweight)
        template = resolve_template(garment_type)
        if not template:
            raise RuntimeError(f"未能通过 garment_type='{garment_type}' 命中内置模板。仅支持 T恤 与 防晒服。")
        pieces_payload = json.loads(Path(template["pieces_path"]).read_text(encoding="utf-8"))
        garment_map = json.loads(Path(template["garment_map_path"]).read_text(encoding="utf-8"))
        pieces_payload, garment_map, template_orientation_issues = normalize_template_payloads(pieces_payload, garment_map)
        template_dir = Path(template["template_dir"])

        # Normalize mask paths to absolute
        for piece in pieces_payload.get("pieces", []):
            mp = piece.get("mask_path", "")
            if mp and not Path(mp).is_absolute():
                piece["mask_path"] = str((template_dir / mp).resolve())
        if template_orientation_issues:
            print(f"[TEMPLATE] Normalized orientation metadata for {len(template_orientation_issues)} fields from template compatibility rules")

        # --- Resume helpers ---
        def _resume_visual() -> dict | None:
            ve_path = work_dir / "visual_elements.json"
            if ve_path.exists():
                print(f"[RESUME] Loading visual_elements from {ve_path}")
                return json.loads(ve_path.read_text(encoding="utf-8"))
            return None

        def _resume_prompt_map() -> dict[str, str] | None:
            prompt_dir = work_dir / "generated_texture_prompts"
            if not prompt_dir.exists():
                return None
            prompt_map = {}
            for f in prompt_dir.glob("*.txt"):
                tid = f.stem
                prompt_map[tid] = f.read_text(encoding="utf-8")
            if prompt_map:
                print(f"[RESUME] Loading {len(prompt_map)} prompts from {prompt_dir}")
                return prompt_map
            return None

        def _resume_texture_prompts() -> dict | None:
            path = work_dir / "texture_prompts.json"
            if path.exists():
                print(f"[RESUME] Loading texture_prompts from {path}")
                return json.loads(path.read_text(encoding="utf-8"))
            return None

        def _resume_hero_path() -> Path | None:
            hero_dir = work_dir / "neo_hero_motif"
            if hero_dir.exists():
                for f in sorted(hero_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                        print(f"[RESUME] Loading hero from {f}")
                        return f
            return None

        def _resume_texture_paths() -> dict[str, Path]:
            texture_root = work_dir / "neo_textures"
            paths = {}
            if texture_root.exists():
                for tid in ["texture_1", "texture_2", "texture_3"]:
                    p = texture_root / f"{tid}.png"
                    if p.exists():
                        print(f"[RESUME] Loading texture {tid} from {p}")
                        paths[tid] = p
            return paths

        def _resume_front_split() -> dict:
            assets_dir = work_dir / "assets"
            if assets_dir.exists():
                full = assets_dir / "theme_front_full.png"
                left = assets_dir / "theme_front_left.png"
                right = assets_dir / "theme_front_right.png"
                if full.exists() and left.exists() and right.exists():
                    return {
                        "full": str(full.resolve()),
                        "left": str(left.resolve()),
                        "right": str(right.resolve()),
                    }
            return {}

        def _has_complete_front_split_assets(split_assets: dict | None) -> bool:
            if not isinstance(split_assets, dict):
                return False
            return bool(split_assets.get("full") and split_assets.get("left") and split_assets.get("right"))

        def _resume_fill_plan() -> tuple[dict, dict, Path, Path] | None:
            tsp = work_dir / "texture_set.json"
            fpp = work_dir / "piece_fill_plan.json"
            if tsp.exists() and fpp.exists():
                ts = json.loads(tsp.read_text(encoding="utf-8"))
                ts["_base_dir"] = str(work_dir.resolve())
                fp = json.loads(fpp.read_text(encoding="utf-8"))
                print(f"[RESUME] Loading fill_plan from {fpp}")
                return ts, fp, tsp, fpp
            return None

        # Pre-start NeoAI upload in parallel with Phase 1
        neo = NeoAIClient()
        ref_url_path = work_dir / "reference_image_url.txt"
        upload_task = None
        if not ref_url_path.exists():
            upload_task = asyncio.create_task(_upload_reference_image(neo, theme_image_path, work_dir, task_id, skip_status=True))

        # Phase 1: Vision analysis
        visual = _resume_visual()
        if visual:
            _write_pipeline_status("analyzing", {"phase": "vision_analysis", "completed_steps": [], "current_step": "vision_analysis (resumed)"})
        else:
            _write_pipeline_status("analyzing", {"phase": "vision_analysis", "completed_steps": [], "current_step": "vision_analysis"})
            vision = VisionService()
            visual = await vision.analyze_theme_image(
                theme_image_path,
                garment_type=garment_type,
                user_prompt=user_prompt,
                hero_prompt_scheme=hero_prompt_scheme,
            )
            _write_json(work_dir / "visual_elements.json", visual)

        # Phase 2: Prompt generation
        prompt_map = _resume_prompt_map()
        texture_prompts = _resume_texture_prompts()
        if prompt_map:
            _write_pipeline_status("analyzing", {"phase": "prompt_generation", "completed_steps": ["vision_analysis"], "current_step": "prompt_generation (resumed)"})
            if not texture_prompts:
                _, texture_prompts = generate_texture_prompts(visual, work_dir, hero_prompt_scheme=hero_prompt_scheme)
                save_texture_prompts(texture_prompts, work_dir)
        else:
            _write_pipeline_status("analyzing", {"phase": "prompt_generation", "completed_steps": ["vision_analysis"], "current_step": "prompt_generation"})
            prompt_map, texture_prompts = generate_texture_prompts(visual, work_dir, hero_prompt_scheme=hero_prompt_scheme)
            save_texture_prompts(texture_prompts, work_dir)
            prompt_dir = work_dir / "generated_texture_prompts"
            prompt_dir.mkdir(parents=True, exist_ok=True)
            for tid, prompt_text in prompt_map.items():
                (prompt_dir / f"{tid}.txt").write_text(prompt_text, encoding="utf-8")

        # Phase 3+: AI asset generation + streaming variants
        model = neo_model or settings.neodomain_default_model
        size = neo_size or settings.neodomain_default_size

        hero_dir = work_dir / "neo_hero_motif"
        texture_root = work_dir / "neo_textures"
        hero_dir.mkdir(parents=True, exist_ok=True)
        texture_root.mkdir(parents=True, exist_ok=True)

        # Wait for parallel upload if it was started
        ref_url = ""
        if upload_task:
            try:
                ref_url = await upload_task
                _update_detail_field(task_id, "reference_image", {"status": "completed", "url": ref_url})
            except Exception as e:
                print(f"[WARN] Reference image upload failed: {e}")
                _update_detail_field(task_id, "reference_image", {"status": "failed"})
                if not settings.skip_ai_generation:
                    raise
        else:
            ref_url = ref_url_path.read_text(encoding="utf-8").strip() if ref_url_path.exists() else ""
            if ref_url:
                _update_detail_field(task_id, "reference_image", {"status": "completed", "url": ref_url})

        # Resume checks
        hero_path = _resume_hero_path()
        texture_paths = _resume_texture_paths()
        texture_errors: dict[str, str] = {}

        # Determine what needs generation
        needs_hero = hero_path is None and not allow_missing_hero
        all_texture_ids = ["texture_1", "texture_2", "texture_3"]
        expected_texture_ids = [tid for tid in (force_render_texture_ids or []) if tid in all_texture_ids] if force_render else list(all_texture_ids)
        if not expected_texture_ids:
            expected_texture_ids = list(texture_paths.keys()) or list(all_texture_ids)
        needs_textures = [tid for tid in expected_texture_ids if tid not in texture_paths]
        # Test mode: wait for manual uploads if assets are missing
        if settings.skip_ai_generation and (needs_hero or needs_textures):
            _write_pipeline_status("waiting_assets", {
                    "phase": "waiting_assets",
                    "completed_steps": ["vision_analysis", "prompt_generation"],
                    "current_step": "waiting_for_manual_uploads",
                    "detail": {
                        "reference_image": {"status": "completed"},
                    "hero_motif": {"status": "pending" if needs_hero else ("deleted" if not hero_path else "completed")},
                    "texture_1": {"status": "pending" if "texture_1" in needs_textures else ("deleted" if force_render and "texture_1" not in expected_texture_ids else "completed")},
                    "texture_2": {"status": "pending" if "texture_2" in needs_textures else ("deleted" if force_render and "texture_2" not in expected_texture_ids else "completed")},
                    "texture_3": {"status": "pending" if "texture_3" in needs_textures else ("deleted" if force_render and "texture_3" not in expected_texture_ids else "completed")},
                },
            })
            return

        # If everything already exists, skip generation and run standard Phase 4-6
        if not needs_hero and not needs_textures:
            print("[RESUME] All AI assets exist, skipping generation.")
            # Standard Phase 4-6
            front_split_assets = _resume_front_split() if hero_path else {}
            if not _has_complete_front_split_assets(front_split_assets) and hero_path:
                try:
                    front_split_assets = create_front_split_assets(hero_path, work_dir)
                except Exception as e:
                    print(f"[WARN] Front split failed: {e}")
                    front_split_assets = {}

            resumed_fill = _resume_fill_plan()
            if resumed_fill:
                texture_set, fill_plan, texture_set_path, fill_plan_path = resumed_fill
                if front_split_assets and not texture_set.get("motifs"):
                    inject_front_split_motifs(texture_set_path, front_split_assets)
                    texture_set = json.loads(texture_set_path.read_text(encoding="utf-8"))
                    texture_set["_base_dir"] = str(work_dir.resolve())
                    # Existing fill plans created before front motifs were injected
                    # do not contain the required front overlay entries.
                    fill_plan = build_fill_plan(pieces_payload, texture_set, garment_map, visual)
                    _write_json(fill_plan_path, fill_plan)
                print("[RESUME] Fill plan already exists, skipping.")
            else:
                texture_set_path = _build_texture_set(work_dir, texture_paths, hero_path, prompt_map)
                if front_split_assets:
                    inject_front_split_motifs(texture_set_path, front_split_assets)

                texture_set = json.loads(texture_set_path.read_text(encoding="utf-8"))
                texture_set["_base_dir"] = str(work_dir.resolve())

                fill_plan = build_fill_plan(pieces_payload, texture_set, garment_map, visual)
                fill_plan_path = work_dir / "piece_fill_plan.json"
                _write_json(fill_plan_path, fill_plan)

            # Phase 6: Render variants
            _write_pipeline_status("rendering", {
                "phase": "rendering",
                "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan"],
                "current_step": "rendering_variants",
                "detail": {
                    "render_runtime": render_runtime,
                },
            })

            variant_summaries = []
            available_texture_ids = list(texture_paths.keys())
            requested_texture_ids = [tid for tid in (force_render_texture_ids or []) if tid in available_texture_ids]
            render_texture_ids = requested_texture_ids or available_texture_ids
            render_texture_ids = [
                tid for tid in available_texture_ids
                if tid in render_texture_ids or not _resume_variant_rendered(work_dir, tid)
            ]
            for texture_id in available_texture_ids:
                should_force_this_variant = force_render and texture_id in render_texture_ids
                if not should_force_this_variant and _resume_variant_rendered(work_dir, texture_id):
                    print(f"[RESUME] Variant {texture_id} already rendered, skipping.")
                    variant_dir = work_dir / "variants" / texture_id
                    variant_texture_set_path = variant_dir / "texture_set.json"
                    variant_fill_plan_path = variant_dir / "piece_fill_plan.json"
                    texture_path = ""
                    for t in texture_set.get("textures", []):
                        if t.get("texture_id") == texture_id:
                            texture_path = t.get("path", "")
                            break
                    variant_summaries.append({
                        "纹理ID": texture_id,
                        "纹理源图": texture_path,
                        "面料组合": str(variant_texture_set_path.resolve()),
                        "裁片填充计划": str(variant_fill_plan_path.resolve()),
                        "渲染目录": str(variant_dir.resolve()),
                        "预览图": str((variant_dir / "preview.png").resolve()),
                        "白底预览图": str((variant_dir / "preview_white.jpg").resolve()),
                    })
                    continue

                variant_dir = work_dir / "variants" / texture_id
                variant_dir.mkdir(parents=True, exist_ok=True)

                variant_set = copy.deepcopy(texture_set)
                variant_set["texture_set_id"] = f"{texture_set.get('texture_set_id', 'texture_set')}_{texture_id}_single_texture"
                variant_set["variant_texture_id"] = texture_id
                variant_set["textures"] = [copy.deepcopy(t) for t in variant_set["textures"] if t.get("texture_id") == texture_id]
                for item in variant_set["textures"]:
                    item["approved"] = True
                    item["candidate"] = False
                    item["role"] = item.get("role") or texture_id
                theme_motifs = [copy.deepcopy(m) for m in texture_set.get("motifs", []) if m.get("motif_id") in {"theme_front_full", "theme_front_left", "theme_front_right"}]
                variant_set["motifs"] = theme_motifs
                if texture_set.get("theme_front_split"):
                    variant_set["theme_front_split"] = copy.deepcopy(texture_set["theme_front_split"])
                variant_texture_set_path = variant_dir / "texture_set.json"
                _write_json(variant_texture_set_path, variant_set)

                variant_fill_plan = _force_fill_plan_to_single_texture(fill_plan, texture_id)
                variant_fill_plan_path = variant_dir / "piece_fill_plan.json"
                _write_json(variant_fill_plan_path, variant_fill_plan)

                print(f"[RENDER] Starting render for variant {texture_id}...")
                rendered = render_all(pieces_payload, variant_set, variant_fill_plan, variant_dir, variant_texture_set_path)
                print(f"[RENDER] Render complete for variant {texture_id}, composing preview...")
                compose_preview(pieces_payload, rendered, variant_dir / "preview.png")
                print(f"[RENDER] Preview composed for variant {texture_id}")
                await _generate_variant_thumbnails(variant_dir, work_dir)

                texture_path = ""
                for t in texture_set.get("textures", []):
                    if t.get("texture_id") == texture_id:
                        texture_path = t.get("path", "")
                        break
                variant_summaries.append({
                    "纹理ID": texture_id,
                    "纹理源图": texture_path,
                    "面料组合": str(variant_texture_set_path.resolve()),
                    "裁片填充计划": str(variant_fill_plan_path.resolve()),
                    "渲染目录": str(variant_dir.resolve()),
                    "预览图": str((variant_dir / "preview.png").resolve()),
                    "白底预览图": str((variant_dir / "preview_white.jpg").resolve()),
                })

            # Write summary
            default_summary = next((s for s in variant_summaries if s["纹理ID"] == "texture_1"), variant_summaries[0] if variant_summaries else None)
            default_rendered_dir = Path(default_summary["渲染目录"]) if default_summary else work_dir / "variants" / "texture_1"

            summary = {
                "单纹理资产": str((work_dir / "neo_textures").resolve()),
                "AI生成透明主图": str(hero_path.resolve()) if hero_path else "",
                "面料组合": str(texture_set_path.resolve()),
                "裁片清单": str(template["pieces_path"]),
                "部位映射": str(template["garment_map_path"]),
                "裁片填充计划": str(fill_plan_path.resolve()),
                "渲染目录": str(default_rendered_dir.resolve()),
                "预览图": str((default_rendered_dir / "preview.png").resolve()),
                "白底预览图": str((default_rendered_dir / "preview_white.jpg").resolve()),
                "裁片模板变体": variant_summaries,
                "部分成功": False,
                "生图错误": {"hero": None, "textures": {}},
                "渲染模式": render_runtime,
            }
            _write_json(work_dir / "automation_summary.json", summary)

            if default_summary:
                root_plan = Path(default_summary["裁片填充计划"])
                if root_plan.exists():
                    shutil.copy2(root_plan, work_dir / "piece_fill_plan.json")

            completed_detail = {
                "render_runtime": render_runtime,
                "reference_image": {"status": "completed"},
                "hero_motif": {"status": ("completed" if hero_path else "deleted"), "path": str(hero_path) if hero_path else ""},
                "texture_1": {"status": "completed" if "texture_1" in texture_paths else "deleted", "path": str(texture_paths.get("texture_1", ""))},
                "texture_2": {"status": "completed" if "texture_2" in texture_paths else "deleted", "path": str(texture_paths.get("texture_2", ""))},
                "texture_3": {"status": "completed" if "texture_3" in texture_paths else "deleted", "path": str(texture_paths.get("texture_3", ""))},
            }
            if preserve_main_status:
                completed_detail["rerender_status"] = "completed"
                completed_detail["rerender_current_step"] = "completed"
            _write_pipeline_status("completed", {
                "phase": "completed",
                "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan", "rendering"],
                "current_step": "completed",
                "detail": completed_detail,
            })
            clear_dirty_assets(task_id, all_assets=True)
            return

        # Create generation tasks
        hero_task = None
        texture_tasks = {}

        if needs_hero:
            hero_task = asyncio.create_task(_gen_hero(
                neo,
                prompt_map.get("hero_motif_1", ""),
                ref_url, model, size, hero_dir, task_id,
            ))

        for tid in needs_textures:
            texture_tasks[tid] = asyncio.create_task(_gen_texture(
                neo, tid,
                prompt_map.get(tid, ""),
                ref_url, model, size, texture_root, task_id,
            ))

        # Stream processing loop
        pending = set()
        if hero_task:
            pending.add(hero_task)
        pending.update(texture_tasks.values())

        texture_id_by_task = {v: k for k, v in texture_tasks.items()}
        hero_retried = False
        hero_error = ""
        front_split_done = False
        front_split_assets = {}
        processed_variants = set()

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is hero_task:
                    result = task.result()
                    if isinstance(result, Exception):
                        if not hero_retried:
                            print("[RETRY] Hero generation failed, retrying once...")
                            hero_retried = True
                            hero_error = str(result)
                            hero_task = asyncio.create_task(_gen_hero(
                                neo,
                                prompt_map.get("hero_motif_1", ""),
                                ref_url, model, size, hero_dir, task_id,
                            ))
                            pending.add(hero_task)
                        else:
                            hero_error = str(result)
                            print(f"[ERROR] Hero generation failed after retry: {result}")
                    else:
                        hero_path = result
                        print(f"[OK] Hero generated: {hero_path}")
                        try:
                            await asyncio.to_thread(generate_thumbnail, hero_path, work_dir / "thumbnails" / hero_path.relative_to(work_dir), _thumb_size_for_role("hero"))
                        except Exception as e:
                            print(f"[WARN] Hero thumbnail generation failed: {e}")
                        if not front_split_done:
                            try:
                                front_split_assets = create_front_split_assets(hero_path, work_dir)
                            except Exception as e:
                                print(f"[WARN] Front split failed: {e}")
                            front_split_done = True
                        # Process any already-completed textures
                        for t_tid in list(texture_paths.keys()):
                            if serial_rendering or t_tid in processed_variants:
                                continue
                            await _process_variant_when_ready(
                                t_tid, texture_paths, hero_path, front_split_assets,
                                prompt_map, pieces_payload, garment_map, visual,
                                work_dir, task_id
                            )
                            processed_variants.add(t_tid)

                elif task in texture_id_by_task:
                    tid = texture_id_by_task[task]
                    result = task.result()
                    if isinstance(result, Exception):
                        texture_errors[tid] = str(result)
                        print(f"[ERROR] Texture {tid} failed: {texture_errors[tid]}")
                    else:
                        texture_paths[tid] = result
                        print(f"[OK] Texture {tid} generated: {result}")
                        try:
                            await asyncio.to_thread(generate_thumbnail, result, work_dir / "thumbnails" / result.relative_to(work_dir), _thumb_size_for_role("texture"))
                        except Exception as e:
                            print(f"[WARN] Texture {tid} thumbnail generation failed: {e}")
                        if not serial_rendering and hero_path and front_split_done and tid not in processed_variants:
                            await _process_variant_when_ready(
                                tid, texture_paths, hero_path, front_split_assets,
                                prompt_map, pieces_payload, garment_map, visual,
                                work_dir, task_id
                            )
                            processed_variants.add(tid)

                # Update status after each task completion
                _write_pipeline_status("generating", {
                    "phase": "neo_ai_generation",
                "completed_steps": ["vision_analysis", "prompt_generation"],
                "current_step": "generating_textures",
                "detail": {
                    "render_runtime": render_runtime,
                    "reference_image": {"status": "completed", "url": ref_url},
                        "hero_motif": {
                            "status": "failed" if (not hero_path and hero_retried and not allow_missing_hero) else ("completed" if hero_path else ("deleted" if allow_missing_hero else "running")),
                            "path": str(hero_path) if hero_path else "",
                            "error": hero_error if (not hero_path and hero_error) else "",
                        },
                        "texture_1": {
                            "status": "completed" if "texture_1" in texture_paths else ("failed" if "texture_1" in texture_errors else "running"),
                            "path": str(texture_paths.get("texture_1", "")),
                            "error": texture_errors.get("texture_1", ""),
                        },
                        "texture_2": {
                            "status": "completed" if "texture_2" in texture_paths else ("failed" if "texture_2" in texture_errors else "running"),
                            "path": str(texture_paths.get("texture_2", "")),
                            "error": texture_errors.get("texture_2", ""),
                        },
                        "texture_3": {
                            "status": "completed" if "texture_3" in texture_paths else ("failed" if "texture_3" in texture_errors else "running"),
                            "path": str(texture_paths.get("texture_3", "")),
                            "error": texture_errors.get("texture_3", ""),
                        },
                    },
                })

        # After loop: check if we have at least one texture
        if not texture_paths:
            hero_status = "failed" if not hero_path else "ok"
            raise RuntimeError(
                f"所有纹理生成失败。hero: {hero_status}, textures: {texture_errors}"
            )

        # Process any textures that completed but hero was not ready at the time
        if not serial_rendering:
            for t_tid in list(texture_paths.keys()):
                if t_tid not in processed_variants and hero_path:
                    await _process_variant_when_ready(
                        t_tid, texture_paths, hero_path, front_split_assets,
                        prompt_map, pieces_payload, garment_map, visual,
                        work_dir, task_id
                    )
                    processed_variants.add(t_tid)

        # Fallback: render any variants not yet processed (e.g. hero failed but textures exist)
        texture_set_path = await asyncio.to_thread(_build_texture_set, work_dir, texture_paths, hero_path, prompt_map)
        if front_split_assets:
            inject_front_split_motifs(texture_set_path, front_split_assets)
        texture_set = json.loads(texture_set_path.read_text(encoding="utf-8"))
        texture_set["_base_dir"] = str(work_dir.resolve())
        fill_plan = await asyncio.to_thread(build_fill_plan, pieces_payload, texture_set, garment_map, visual)
        fill_plan_path = work_dir / "piece_fill_plan.json"
        _write_json(fill_plan_path, fill_plan)

        variant_summaries = []
        for texture_id in list(texture_paths.keys()):
            if texture_id in processed_variants:
                variant_dir = work_dir / "variants" / texture_id
                variant_texture_set_path = variant_dir / "texture_set.json"
                variant_fill_plan_path = variant_dir / "piece_fill_plan.json"
                texture_path = ""
                for t in texture_set.get("textures", []):
                    if t.get("texture_id") == texture_id:
                        texture_path = t.get("path", "")
                        break
                variant_summaries.append({
                    "纹理ID": texture_id,
                    "纹理源图": texture_path,
                    "面料组合": str(variant_texture_set_path.resolve()),
                    "裁片填充计划": str(variant_fill_plan_path.resolve()),
                    "渲染目录": str(variant_dir.resolve()),
                    "预览图": str((variant_dir / "preview.png").resolve()),
                    "白底预览图": str((variant_dir / "preview_white.jpg").resolve()),
                })
            else:
                variant_dir = work_dir / "variants" / texture_id
                variant_dir.mkdir(parents=True, exist_ok=True)

                variant_set = copy.deepcopy(texture_set)
                variant_set["texture_set_id"] = f"{texture_set.get('texture_set_id', 'texture_set')}_{texture_id}_single_texture"
                variant_set["variant_texture_id"] = texture_id
                variant_set["textures"] = [copy.deepcopy(t) for t in variant_set["textures"] if t.get("texture_id") == texture_id]
                for item in variant_set["textures"]:
                    item["approved"] = True
                    item["candidate"] = False
                    item["role"] = item.get("role") or texture_id
                theme_motifs = [copy.deepcopy(m) for m in texture_set.get("motifs", []) if m.get("motif_id") in {"theme_front_full", "theme_front_left", "theme_front_right"}]
                variant_set["motifs"] = theme_motifs
                if texture_set.get("theme_front_split"):
                    variant_set["theme_front_split"] = copy.deepcopy(texture_set["theme_front_split"])
                variant_texture_set_path = variant_dir / "texture_set.json"
                _write_json(variant_texture_set_path, variant_set)

                variant_fill_plan = _force_fill_plan_to_single_texture(fill_plan, texture_id)
                variant_fill_plan_path = variant_dir / "piece_fill_plan.json"
                _write_json(variant_fill_plan_path, variant_fill_plan)

                rendered = render_all(pieces_payload, variant_set, variant_fill_plan, variant_dir, variant_texture_set_path)
                compose_preview(pieces_payload, rendered, variant_dir / "preview.png")
                await _generate_variant_thumbnails(variant_dir, work_dir)

                texture_path = ""
                for t in texture_set.get("textures", []):
                    if t.get("texture_id") == texture_id:
                        texture_path = t.get("path", "")
                        break
                variant_summaries.append({
                    "纹理ID": texture_id,
                    "纹理源图": texture_path,
                    "面料组合": str(variant_texture_set_path.resolve()),
                    "裁片填充计划": str(variant_fill_plan_path.resolve()),
                    "渲染目录": str(variant_dir.resolve()),
                    "预览图": str((variant_dir / "preview.png").resolve()),
                    "白底预览图": str((variant_dir / "preview_white.jpg").resolve()),
                })

        # Write summary
        default_summary = next((s for s in variant_summaries if s["纹理ID"] == "texture_1"), variant_summaries[0] if variant_summaries else None)
        default_rendered_dir = Path(default_summary["渲染目录"]) if default_summary else work_dir / "variants" / "texture_1"

        summary = {
            "单纹理资产": str((work_dir / "neo_textures").resolve()),
            "AI生成透明主图": str(hero_path.resolve()) if hero_path else "",
            "面料组合": str(texture_set_path.resolve()),
            "裁片清单": str(template["pieces_path"]),
            "部位映射": str(template["garment_map_path"]),
            "裁片填充计划": str(fill_plan_path.resolve()),
            "渲染目录": str(default_rendered_dir.resolve()),
            "预览图": str((default_rendered_dir / "preview.png").resolve()),
            "白底预览图": str((default_rendered_dir / "preview_white.jpg").resolve()),
            "裁片模板变体": variant_summaries,
            "部分成功": bool(texture_errors or not hero_path),
            "生图错误": {"hero": "failed" if not hero_path else None, "textures": texture_errors},
            "渲染模式": render_runtime,
        }
        _write_json(work_dir / "automation_summary.json", summary)

        if default_summary:
            root_plan = Path(default_summary["裁片填充计划"])
            if root_plan.exists():
                shutil.copy2(root_plan, work_dir / "piece_fill_plan.json")

        completed_detail = {
            "render_runtime": render_runtime,
            "reference_image": {"status": "completed"},
            "hero_motif": {
                "status": ("completed" if hero_path else ("deleted" if allow_missing_hero else "failed")),
                "path": str(hero_path) if hero_path else "",
                "error": hero_error if (not hero_path and hero_error) else "",
            },
            "texture_1": {"status": "completed" if "texture_1" in texture_paths else "failed", "path": str(texture_paths.get("texture_1", "")), "error": texture_errors.get("texture_1", "")},
            "texture_2": {"status": "completed" if "texture_2" in texture_paths else "failed", "path": str(texture_paths.get("texture_2", "")), "error": texture_errors.get("texture_2", "")},
            "texture_3": {"status": "completed" if "texture_3" in texture_paths else "failed", "path": str(texture_paths.get("texture_3", "")), "error": texture_errors.get("texture_3", "")},
        }
        if preserve_main_status:
            completed_detail["rerender_status"] = "completed"
            completed_detail["rerender_current_step"] = "completed"
        _write_pipeline_status("completed", {
            "phase": "completed",
            "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan", "rendering"],
            "current_step": "completed",
            "detail": completed_detail,
        })
        clear_dirty_assets(task_id, all_assets=True)

    except Exception as exc:
        import traceback
        _write_pipeline_status("failed", error=f"{exc}\n{traceback.format_exc()}")
        raise
