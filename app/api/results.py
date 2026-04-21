"""Result download and preview API endpoints."""
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.models.schemas import AutomationSummary

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


@router.get("/tasks/{task_id}/theme_image")
async def get_theme_image(task_id: str):
    """Get the original uploaded theme image."""
    task_dir = _task_dir(task_id)
    theme_inputs_dir = task_dir / "theme_inputs"
    if theme_inputs_dir.exists():
        for f in theme_inputs_dir.iterdir():
            if f.name.startswith("theme_image"):
                suffix = f.suffix.lower()
                media_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".bmp": "image/bmp",
                }
                return FileResponse(f, media_type=media_types.get(suffix, "application/octet-stream"))
    raise HTTPException(status_code=404, detail="主题图不存在")


@router.get("/tasks/{task_id}/hero_motif")
async def get_hero_motif(task_id: str):
    """Get the generated hero motif image."""
    task_dir = _task_dir(task_id)
    hero_dir = task_dir / "neo_hero_motif"
    if hero_dir.exists():
        for f in sorted(hero_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = f.suffix.lower()
                media_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }
                return FileResponse(f, media_type=media_types.get(suffix, "application/octet-stream"))
    raise HTTPException(status_code=404, detail="主图尚未生成")


@router.get("/tasks/{task_id}/textures/{texture_id}")
async def get_texture(task_id: str, texture_id: str):
    """Get a generated texture image."""
    if texture_id not in {"main", "secondary", "accent_light"}:
        raise HTTPException(status_code=400, detail="无效的纹理ID")
    task_dir = _task_dir(task_id)
    path = task_dir / "neo_textures" / f"{texture_id}.png"
    if path.exists():
        return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="纹理图尚未生成")


@router.get("/tasks/{task_id}/preview")
async def get_preview(task_id: str, variant: str = ""):
    """Get the main preview image (PNG with transparent background)."""
    if variant:
        path = _task_dir(task_id) / "variants" / variant / "preview.png"
        if path.exists():
            return FileResponse(path, media_type="image/png")
    path = _task_dir(task_id) / "variants" / "main" / "preview.png"
    if not path.exists():
        for v in ["main", "secondary", "accent_light"]:
            path = _task_dir(task_id) / "variants" / v / "preview.png"
            if path.exists():
                break
    if not path.exists():
        raise HTTPException(status_code=404, detail="预览图尚未生成")
    return FileResponse(path, media_type="image/png")


@router.get("/tasks/{task_id}/front_pair_check")
async def get_front_pair_check(task_id: str, variant: str = ""):
    """Get the front pair check image for a variant."""
    if variant:
        path = _task_dir(task_id) / "variants" / variant / "front_pair_check.png"
    else:
        path = _task_dir(task_id) / "variants" / "main" / "front_pair_check.png"
        if not path.exists():
            for v in ["main", "secondary", "accent_light"]:
                path = _task_dir(task_id) / "variants" / v / "front_pair_check.png"
                if path.exists():
                    break
    if not path.exists():
        raise HTTPException(status_code=404, detail="front_pair_check 不存在")
    return FileResponse(path, media_type="image/png")


@router.get("/tasks/{task_id}/preview_white")
async def get_preview_white(task_id: str, variant: str = ""):
    """Get the white-background preview image (JPG)."""
    if variant:
        path = _task_dir(task_id) / "variants" / variant / "preview_white.jpg"
        if path.exists():
            return FileResponse(path, media_type="image/jpeg")
    path = _task_dir(task_id) / "variants" / "main" / "preview_white.jpg"
    if not path.exists():
        for v in ["main", "secondary", "accent_light"]:
            path = _task_dir(task_id) / "variants" / v / "preview_white.jpg"
            if path.exists():
                break
    if not path.exists():
        raise HTTPException(status_code=404, detail="白底预览图尚未生成")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/tasks/{task_id}/pieces/{piece_id}")
async def get_piece(task_id: str, piece_id: str):
    """Get a single rendered piece PNG."""
    # Search in main variant first
    for variant in ["main", "secondary", "accent_light"]:
        path = _task_dir(task_id) / "variants" / variant / "pieces" / f"{piece_id}.png"
        if path.exists():
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
    _update_detail_field(task_id, "hero_motif", {"status": "completed", "path": str(dest.resolve())})
    return {"ok": True, "path": str(dest.resolve())}


@router.post("/tasks/{task_id}/textures/{texture_id}")
async def upload_texture(task_id: str, texture_id: str, file: UploadFile = File(...)):
    """Manually upload a texture image."""
    if texture_id not in {"main", "secondary", "accent_light"}:
        raise HTTPException(status_code=400, detail="无效的纹理ID")
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    texture_dir = task_dir / "neo_textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    dest = texture_dir / f"{texture_id}.png"
    dest.write_bytes(data)
    _update_detail_field(task_id, texture_id, {"status": "completed", "path": str(dest.resolve())})
    return {"ok": True, "path": str(dest.resolve())}


@router.get("/tasks/{task_id}/download")
async def download_results(task_id: str):
    """Download preview PNGs as a ZIP archive (preview1/2/3.png only)."""
    task_dir = _task_dir(task_id)
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    png_map = {"main": "preview1.png", "secondary": "preview2.png", "accent_light": "preview3.png"}
    svg_map = {"main": "preview1.svg", "secondary": "preview2.svg", "accent_light": "preview3.svg"}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        variants_dir = task_dir / "variants"
        if variants_dir.exists():
            for variant_name, zip_name in png_map.items():
                preview = variants_dir / variant_name / "preview.png"
                if preview.exists():
                    zf.write(preview, zip_name)
            for variant_name, zip_name in svg_map.items():
                preview = variants_dir / variant_name / "preview.svg"
                if preview.exists():
                    zf.write(preview, zip_name)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=auto_garment_{task_id}.zip"},
    )
