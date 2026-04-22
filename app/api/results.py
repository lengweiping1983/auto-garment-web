"""Result download and preview API endpoints."""
import asyncio
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.core.pipeline import mark_dirty_assets
from app.core.image_utils import delete_thumbnail, ensure_thumbnail, _thumb_size_for_role
from app.models.schemas import AutomationSummary

try:
    import vtracer
except Exception:
    vtracer = None

router = APIRouter()


def _task_dir(task_id: str) -> Path:
    return settings.storage_base_dir / task_id


def _update_detail_field(task_id: str, key: str, value: dict):
    """Update a single field in progress.detail without changing overall status."""
    path = _task_dir(task_id) / "status.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    progress = data.get("progress") or {}
    detail = progress.get("detail") or {}
    detail[key] = value
    progress["detail"] = detail
    data["progress"] = progress
    data["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary_path(task_id: str) -> Path:
    return _task_dir(task_id) / "automation_summary.json"


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix, "application/octet-stream")


@router.get("/tasks/{task_id}/theme_image")
async def get_theme_image(task_id: str, thumb: bool = False):
    """Get the original uploaded theme image (or its thumbnail)."""
    task_dir = _task_dir(task_id)
    theme_inputs_dir = task_dir / "theme_inputs"
    if theme_inputs_dir.exists():
        for f in theme_inputs_dir.iterdir():
            if f.name.startswith("theme_image"):
                if thumb:
                    try:
                        thumb_path = await asyncio.to_thread(ensure_thumbnail, f, task_dir, _thumb_size_for_role("theme"))
                        return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
                    except Exception:
                        pass
                return FileResponse(f, media_type=_image_media_type(f))
    raise HTTPException(status_code=404, detail="主题图不存在")


@router.get("/tasks/{task_id}/hero_motif")
async def get_hero_motif(task_id: str, thumb: bool = False):
    """Get the generated hero motif image (or its thumbnail)."""
    task_dir = _task_dir(task_id)
    hero_dir = task_dir / "neo_hero_motif"
    if hero_dir.exists():
        for f in sorted(hero_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                if thumb:
                    try:
                        thumb_path = await asyncio.to_thread(ensure_thumbnail, f, task_dir, _thumb_size_for_role("hero"))
                        return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
                    except Exception:
                        pass
                return FileResponse(f, media_type=_image_media_type(f))
    raise HTTPException(status_code=404, detail="主图尚未生成")


@router.get("/tasks/{task_id}/textures/{texture_id}")
async def get_texture(task_id: str, texture_id: str, thumb: bool = False):
    """Get a generated texture image (or its thumbnail)."""
    if texture_id not in {"texture_1", "texture_2", "texture_3"}:
        raise HTTPException(status_code=400, detail="无效的纹理ID")
    task_dir = _task_dir(task_id)
    path = task_dir / "neo_textures" / f"{texture_id}.png"
    if path.exists():
        if thumb:
            try:
                thumb_path = await asyncio.to_thread(ensure_thumbnail, path, task_dir, _thumb_size_for_role("texture"))
                return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
            except Exception:
                pass
        return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="纹理图尚未生成")


@router.get("/tasks/{task_id}/preview")
async def get_preview(task_id: str, variant: str = "", thumb: bool = False):
    """Get the main preview image (PNG with transparent background)."""
    if not variant:
        raise HTTPException(status_code=400, detail="必须指定 variant")
    task_dir = _task_dir(task_id)
    path = task_dir / "variants" / variant / "preview.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="预览图尚未生成")
    if thumb:
        try:
            thumb_path = await asyncio.to_thread(ensure_thumbnail, path, task_dir, _thumb_size_for_role("preview"))
            return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
        except Exception:
            pass
    return FileResponse(path, media_type="image/png")


@router.get("/tasks/{task_id}/front_pair_check")
async def get_front_pair_check(task_id: str, variant: str = "", thumb: bool = False):
    """Get the front pair check image for a variant."""
    if not variant:
        raise HTTPException(status_code=400, detail="必须指定 variant")
    task_dir = _task_dir(task_id)
    path = task_dir / "variants" / variant / "front_pair_check.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="front_pair_check 不存在")
    if thumb:
        try:
            thumb_path = await asyncio.to_thread(ensure_thumbnail, path, task_dir, _thumb_size_for_role("front_pair_check"))
            return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
        except Exception:
            pass
    return FileResponse(path, media_type="image/png")


@router.get("/tasks/{task_id}/preview_white")
async def get_preview_white(task_id: str, variant: str = "", thumb: bool = False):
    """Get the white-background preview image (JPG)."""
    if not variant:
        raise HTTPException(status_code=400, detail="必须指定 variant")
    task_dir = _task_dir(task_id)
    path = task_dir / "variants" / variant / "preview_white.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="白底预览图尚未生成")
    if thumb:
        try:
            thumb_path = await asyncio.to_thread(ensure_thumbnail, path, task_dir, _thumb_size_for_role("preview_white"))
            return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
        except Exception:
            pass
    return FileResponse(path, media_type="image/jpeg")


@router.get("/tasks/{task_id}/pieces/{piece_id}")
async def get_piece(task_id: str, piece_id: str, variant: str = "", thumb: bool = False):
    """Get a single rendered piece PNG (or its thumbnail)."""
    if not variant:
        raise HTTPException(status_code=400, detail="必须指定 variant")
    task_dir = _task_dir(task_id)
    path = task_dir / "variants" / variant / "pieces" / f"{piece_id}.png"
    if path.exists():
        if thumb:
            try:
                thumb_path = await asyncio.to_thread(ensure_thumbnail, path, task_dir, _thumb_size_for_role("piece"))
                return FileResponse(thumb_path, media_type=_image_media_type(thumb_path))
            except Exception:
                pass
        return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="裁片不存在或尚未生成")


@router.get("/tasks/{task_id}/summary")
async def get_summary(task_id: str):
    """Get automation_summary.json."""
    path = _summary_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="摘要文件尚未生成")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["task_id"] = task_id
    return data


@router.post("/tasks/{task_id}/theme_image")
async def replace_theme_image(task_id: str, file: UploadFile = File(...)):
    """Replace the theme image for a task."""
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    theme_inputs_dir = task_dir / "theme_inputs"
    theme_inputs_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing theme images
    for f in theme_inputs_dir.iterdir():
        if f.name.startswith("theme_image"):
            f.unlink()

    # Clear cached reference URL so it gets re-uploaded on next pipeline run
    ref_url_path = task_dir / "reference_image_url.txt"
    if ref_url_path.exists():
        ref_url_path.unlink()

    suffix = Path(file.filename or "upload.png").suffix
    if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        suffix = ".png"
    dest = theme_inputs_dir / f"theme_image{suffix}"
    data = await file.read()
    dest.write_bytes(data)
    _update_detail_field(task_id, "reference_image", {"status": "completed", "path": str(dest.resolve())})
    return {"ok": True, "path": str(dest.resolve())}


@router.post("/tasks/{task_id}/hero_motif")
async def upload_hero_motif(task_id: str, file: UploadFile = File(...)):
    """Manually upload hero motif image."""
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    hero_dir = task_dir / "neo_hero_motif"
    hero_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.png").suffix
    if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    dest = hero_dir / f"hero_motif{suffix}"
    data = await file.read()
    dest.write_bytes(data)
    try:
        await asyncio.to_thread(ensure_thumbnail, dest, task_dir, _thumb_size_for_role("hero"))
    except Exception as e:
        print(f"[WARN] Hero thumbnail generation failed for {dest}: {e}")
    _update_detail_field(task_id, "hero_motif", {"status": "completed", "path": str(dest.resolve())})
    mark_dirty_assets(task_id, hero=True)
    return {"ok": True, "path": str(dest.resolve())}


@router.delete("/tasks/{task_id}/hero_motif")
async def delete_hero_motif(task_id: str):
    """Delete the manually generated/uploaded hero motif image."""
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    hero_dir = task_dir / "neo_hero_motif"
    if hero_dir.exists():
        for f in hero_dir.iterdir():
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                delete_thumbnail(f, task_dir)
                f.unlink()

    # Clear derived front-split assets so rerender cannot reuse stale hero-based motifs.
    assets_dir = task_dir / "assets"
    if assets_dir.exists():
        for name in ("theme_front_full.png", "theme_front_left.png", "theme_front_right.png"):
            path = assets_dir / name
            if path.exists():
                path.unlink()

    _update_detail_field(task_id, "hero_motif", {"status": "deleted", "path": "", "error": ""})
    mark_dirty_assets(task_id, hero=True)
    return {"ok": True, "deleted": True}


@router.post("/tasks/{task_id}/textures/{texture_id}")
async def upload_texture(task_id: str, texture_id: str, file: UploadFile = File(...)):
    """Manually upload a texture image."""
    if texture_id not in {"texture_1", "texture_2", "texture_3"}:
        raise HTTPException(status_code=400, detail="无效的纹理ID")
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    texture_dir = task_dir / "neo_textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    dest = texture_dir / f"{texture_id}.png"
    dest.write_bytes(data)
    try:
        await asyncio.to_thread(ensure_thumbnail, dest, task_dir, _thumb_size_for_role("texture"))
    except Exception as e:
        print(f"[WARN] Texture thumbnail generation failed for {dest}: {e}")
    _update_detail_field(task_id, texture_id, {"status": "completed", "path": str(dest.resolve())})
    mark_dirty_assets(task_id, textures=[texture_id])
    return {"ok": True, "path": str(dest.resolve())}


@router.delete("/tasks/{task_id}/textures/{texture_id}")
async def delete_texture(task_id: str, texture_id: str):
    """Delete a manually generated/uploaded texture image."""
    if texture_id not in {"texture_1", "texture_2", "texture_3"}:
        raise HTTPException(status_code=400, detail="无效的纹理ID")

    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    path = task_dir / "neo_textures" / f"{texture_id}.png"
    if path.exists():
        delete_thumbnail(path, task_dir)
        path.unlink()

    _update_detail_field(task_id, texture_id, {"status": "deleted", "path": "", "error": ""})
    mark_dirty_assets(task_id, textures=[texture_id])
    return {"ok": True, "deleted": True}


def _ensure_svg(png_path: Path, svg_path: Path) -> bool:
    """Convert PNG to SVG using vtracer if SVG does not exist."""
    if svg_path.exists():
        return True
    if not png_path.exists():
        return False
    if vtracer is None:
        return False
    try:
        vtracer.convert_image_to_svg_py(str(png_path), str(svg_path))
        return svg_path.exists()
    except Exception as e:
        print(f"[WARN] PNG to SVG conversion failed for {png_path}: {e}")
        return False


def _build_ext_zip(task_dir: Path, ext: str) -> io.BytesIO:
    """Build ZIP buffer for a single file extension (png or svg),
    including previews for all variants."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        variants_dir = task_dir / "variants"
        if variants_dir.exists():
            for i, variant_name in enumerate(["texture_1", "texture_2", "texture_3"], 1):
                # Preview
                file_path = variants_dir / variant_name / f"preview.{ext}"
                if file_path.exists():
                    zf.write(file_path, f"preview{i}.{ext}")
    buffer.seek(0)
    return buffer


@router.get("/tasks/{task_id}/download")
async def download_results(task_id: str):
    """Download preview PNGs and SVGs as a ZIP archive (backward compat)."""
    return await _download_package(task_id, "pngsvg")


@router.get("/tasks/{task_id}/download/png")
async def download_png_package(task_id: str):
    """Download preview PNGs as a ZIP archive."""
    return await _download_package(task_id, "png")


@router.get("/tasks/{task_id}/download/svg")
async def download_svg_package(task_id: str):
    """Download preview SVGs as a ZIP archive."""
    return await _download_package(task_id, "svg")


async def _download_package(task_id: str, kind: str):
    """Internal: build and return a ZIP of PNGs, SVGs, or both."""
    import asyncio
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    variants_dir = task_dir / "variants"
    if variants_dir.exists() and kind in ("svg", "pngsvg"):
        # Pre-generate missing SVGs (serial, one by one)
        for variant_name in ["texture_1", "texture_2", "texture_3"]:
            svg_path = variants_dir / variant_name / "preview.svg"
            if not svg_path.exists():
                png_path = variants_dir / variant_name / "preview.png"
                if png_path.exists():
                    try:
                        await asyncio.to_thread(_ensure_svg, png_path, svg_path)
                    except Exception:
                        pass

    if kind == "png":
        buffer = await asyncio.to_thread(_build_ext_zip, task_dir, "png")
        filename = f"{task_id}.zip"
    elif kind == "svg":
        buffer = await asyncio.to_thread(_build_ext_zip, task_dir, "svg")
        filename = f"{task_id}.zip"
    else:
        # pngsvg — backward compat, both in one zip, now includes pieces/
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if variants_dir.exists():
                for i, variant_name in enumerate(["texture_1", "texture_2", "texture_3"], 1):
                    png_path = variants_dir / variant_name / "preview.png"
                    if png_path.exists():
                        zf.write(png_path, f"preview{i}.png")
                    svg_path = variants_dir / variant_name / "preview.svg"
                    if svg_path.exists():
                        zf.write(svg_path, f"preview{i}.svg")
                    # Individual pieces
                    pieces_dir = variants_dir / variant_name / "pieces"
                    if pieces_dir.exists():
                        for piece_file in sorted(pieces_dir.glob("*.png")):
                            arcname = f"pieces/{variant_name}/{piece_file.name}"
                            zf.write(piece_file, arcname)
        buffer.seek(0)
        filename = f"{task_id}.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
