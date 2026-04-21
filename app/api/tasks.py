"""Task management API endpoints."""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.config import settings
from app.core.image_utils import resolve_theme_image
from app.core.pipeline import clear_front_split_assets, clear_rerender_outputs, read_dirty_assets, read_task_status, run_pipeline
from app.models.schemas import GarmentType, TaskCreateResponse, TaskStatusResponse

router = APIRouter()


def _validate_garment_type(garment_type: str) -> str:
    valid_types = {"T恤", "防晒服", "t-shirt", "tee", "衬衫", "男士衬衫", "防晒衣", "sun protection clothing"}
    if garment_type in valid_types:
        return garment_type
    gt = garment_type.strip().lower()
    if "t" in gt or "shirt" in gt or "tee" in gt:
        return "T恤"
    elif "防晒" in gt or "sun" in gt:
        return "防晒服"
    raise HTTPException(status_code=400, detail=f"不支持的服装类型: {garment_type}。仅支持 T恤 和 防晒服。")


@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(
    background_tasks: BackgroundTasks,
    theme_image: UploadFile = File(...),
    garment_type: str = Form(...),
    user_prompt: str = Form(""),
    neo_model: str = Form(""),
    neo_size: str = Form(""),
):
    """Create a new garment production task."""
    task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    work_dir = settings.storage_base_dir / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded image
    theme_inputs_dir = work_dir / "theme_inputs"
    theme_inputs_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(theme_image.filename or "upload.png").suffix
    if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        suffix = ".png"
    theme_path = theme_inputs_dir / f"theme_image{suffix}"
    with open(theme_path, "wb") as f:
        shutil.copyfileobj(theme_image.file, f)

    garment_type = _validate_garment_type(garment_type)

    # Save task config for later resume/render
    config_path = work_dir / "task_config.json"
    config_path.write_text(
        json.dumps({
            "garment_type": garment_type,
            "user_prompt": user_prompt,
            "neo_model": neo_model,
            "neo_size": neo_size,
            "hero_prompt_scheme": "b",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Start pipeline in background
    background_tasks.add_task(
        run_pipeline,
        task_id=task_id,
        theme_image_path=theme_path,
        garment_type=garment_type,
        user_prompt=user_prompt,
        neo_model=neo_model,
        neo_size=neo_size,
        hero_prompt_scheme="b",
    )

    return TaskCreateResponse(
        task_id=task_id,
        status="pending",
        created_at=datetime.now(),
        message="任务已创建，正在后台处理",
    )


@router.get("/tasks")
async def list_tasks():
    """List all tasks in storage directory."""
    tasks = []
    storage_dir = settings.storage_base_dir
    if not storage_dir.exists():
        return {"tasks": tasks}

    for task_dir in sorted(storage_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not task_dir.is_dir():
            continue
        task_id = task_dir.name
        status_file = task_dir / "status.json"
        status_data = {"status": "unknown", "updated_at": ""}
        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Check for theme image
        theme_inputs_dir = task_dir / "theme_inputs"
        has_theme_image = any(theme_inputs_dir.glob("theme_image*")) if theme_inputs_dir.exists() else False

        # Check for preview
        has_preview = any(task_dir.rglob("preview.png"))

        user_prompt = status_data.get("user_prompt", "")
        display_name = task_id
        if display_name.startswith("agp_"):
            display_name = display_name[4:]
        if user_prompt:
            display_name = user_prompt[:10] + ("" if len(user_prompt) <= 10 else "…")

        tasks.append({
            "task_id": task_id,
            "display_name": display_name,
            "status": status_data.get("status", "unknown"),
            "updated_at": status_data.get("updated_at", ""),
            "has_theme_image": has_theme_image,
            "has_preview": has_preview,
        })

    return {"tasks": tasks}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    garment_type: str = Form(...),
    user_prompt: str = Form(""),
    neo_model: str = Form(""),
    neo_size: str = Form(""),
):
    """Retry an existing task with the saved theme image."""
    work_dir = settings.storage_base_dir / task_id
    if not work_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    # Find existing theme image
    theme_inputs_dir = work_dir / "theme_inputs"
    theme_path = None
    if theme_inputs_dir.exists():
        for f in theme_inputs_dir.iterdir():
            if f.name.startswith("theme_image"):
                theme_path = f
                break

    if not theme_path or not theme_path.exists():
        raise HTTPException(status_code=404, detail="任务主题图不存在，无法重试")

    garment_type = _validate_garment_type(garment_type)

    # Reset status
    status_file = work_dir / "status.json"
    if status_file.exists():
        status_data = json.loads(status_file.read_text(encoding="utf-8"))
        status_data["status"] = "pending"
        status_data["error"] = None
        status_data["updated_at"] = datetime.now().isoformat()
        status_file.write_text(json.dumps(status_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Start pipeline in background
    background_tasks.add_task(
        run_pipeline,
        task_id=task_id,
        theme_image_path=theme_path,
        garment_type=garment_type,
        user_prompt=user_prompt,
        neo_model=neo_model,
        neo_size=neo_size,
        hero_prompt_scheme="b",
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已重新启动",
    }


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get task status and progress."""
    status = read_task_status(task_id)
    if status.get("status") == "unknown":
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_id=status.get("task_id", task_id),
        status=status.get("status", "unknown"),
        progress=status.get("progress"),
        error=status.get("error"),
        created_at=None,
        updated_at=None,
    )


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task and all its files."""
    work_dir = settings.storage_base_dir / task_id
    if not work_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        shutil.rmtree(work_dir)
        return {"ok": True, "message": "任务已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.post("/tasks/{task_id}/continue_render")
async def continue_render(task_id: str, background_tasks: BackgroundTasks):
    """Skip AI generation and continue with rendering when all assets are manually uploaded."""
    work_dir = settings.storage_base_dir / task_id
    if not work_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    # Check required assets
    hero_dir = work_dir / "neo_hero_motif"
    hero_path = None
    if hero_dir.exists():
        for f in sorted(hero_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                hero_path = f
                break

    texture_root = work_dir / "neo_textures"
    texture_paths = {}
    if texture_root.exists():
        for tid in ["texture_1", "texture_2", "texture_3"]:
            p = texture_root / f"{tid}.png"
            if p.exists():
                texture_paths[tid] = p

    if not texture_paths:
        raise HTTPException(status_code=400, detail="重新渲染至少需要保留 1 张纹理")

    # Find theme image
    theme_inputs_dir = work_dir / "theme_inputs"
    theme_path = None
    if theme_inputs_dir.exists():
        for f in theme_inputs_dir.iterdir():
            if f.name.startswith("theme_image"):
                theme_path = f
                break
    if not theme_path or not theme_path.exists():
        raise HTTPException(status_code=404, detail="任务主题图不存在")

    # Read task config
    config_path = work_dir / "task_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {}

    garment_type = config.get("garment_type", "T恤")
    user_prompt = config.get("user_prompt", "")
    neo_model = config.get("neo_model", "")
    neo_size = config.get("neo_size", "")
    hero_prompt_scheme = config.get("hero_prompt_scheme", "b")
    dirty_assets = read_dirty_assets(task_id)
    target_texture_ids = list(texture_paths.keys())

    clear_rerender_outputs(task_id)
    if dirty_assets.get("hero") and not hero_path:
        clear_front_split_assets(task_id)

    # Update status before starting
    from app.core.pipeline import _write_status
    _write_status(task_id, "rendering", {
        "phase": "rendering",
        "completed_steps": ["vision_analysis", "prompt_generation", "neo_ai_generation", "front_split", "fill_plan"],
        "current_step": "rendering_variants",
        "detail": {
            "rerender_scope": {
                "hero_changed": bool(dirty_assets.get("hero")),
                "texture_ids": target_texture_ids,
            },
        },
    })

    background_tasks.add_task(
        run_pipeline,
        task_id=task_id,
        theme_image_path=theme_path,
        garment_type=garment_type,
        user_prompt=user_prompt,
        neo_model=neo_model,
        neo_size=neo_size,
        hero_prompt_scheme=hero_prompt_scheme,
        force_render=True,
        force_render_texture_ids=target_texture_ids,
        allow_missing_hero=True,
    )

    return {
        "task_id": task_id,
        "status": "rendering",
        "message": "已开始渲染，所有资产已就绪",
        "rerender_scope": {
            "hero_changed": bool(dirty_assets.get("hero")),
            "texture_ids": target_texture_ids,
        },
    }
