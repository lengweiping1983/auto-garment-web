"""Pydantic schemas for request/response models."""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GarmentType(str, Enum):
    T_SHIRT = "T恤"
    SUN_PROTECTION = "防晒服"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class StyleInfo(BaseModel):
    medium: str = ""
    mood: str = ""
    brush_quality: str = ""
    pattern_density: str = "low"


class Palette(BaseModel):
    primary: list[str] = []
    secondary: list[str] = []
    accent: list[str] = []
    dark: list[str] = []


class VisualElements(BaseModel):
    palette: Palette = Field(default_factory=Palette)
    style: StyleInfo = Field(default_factory=StyleInfo)
    dominant_subject: str = ""
    motif_vocabulary: list[str] = []
    fusion_rule: str = ""


class PromptSet(BaseModel):
    main: str = ""
    secondary: str = ""
    accent_light: str = ""
    hero: str = ""


class GenerationDetail(BaseModel):
    hero_motif: str = "pending"
    main: str = "pending"
    secondary: str = "pending"
    accent_light: str = "pending"


class TaskProgress(BaseModel):
    phase: str = ""
    completed_steps: list[str] = []
    current_step: str = ""
    detail: GenerationDetail = Field(default_factory=GenerationDetail)


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: datetime
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: TaskProgress | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AutomationSummary(BaseModel):
    task_id: str
    texture_set_path: str = ""
    hero_motif_path: str = ""
    piece_fill_plan_path: str = ""
    preview_path: str = ""
    preview_white_path: str = ""
    variants: list[dict[str, Any]] = []
    pieces: list[dict[str, Any]] = []
