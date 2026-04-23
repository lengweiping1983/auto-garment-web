"""Shared interfaces and helpers for hero prompt generation strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import re
from pathlib import Path

try:
    from app.core.prompt_sanitizer import normalize_image_generation_prompt
except Exception:
    def normalize_image_generation_prompt(prompt, strict=False):
        return prompt


VALID_HERO_PROMPT_SCHEMES = {"a", "b"}

_PROMPT_JUNK_CHUNKS = {
    "on",
    "in",
    "at",
    "with",
    "feeling",
    "mockup feeling",
    "garment mockup feeling",
}


def validate_hero_prompt_scheme(hero_prompt_scheme: str) -> str:
    scheme = (hero_prompt_scheme or "b").strip().lower()
    if scheme not in VALID_HERO_PROMPT_SCHEMES:
        raise ValueError(
            f"Unsupported hero_prompt_scheme='{hero_prompt_scheme}'. Expected one of: "
            + ", ".join(sorted(VALID_HERO_PROMPT_SCHEMES))
        )
    return scheme


def clean_prompt_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"([,.;:!?]){2,}", r"\1", text)
    return text.strip(" ,;")


def dedupe_prompt_chunks(text: str) -> str:
    chunks = [chunk.strip() for chunk in re.split(r"\s*,\s*", text or "") if chunk.strip()]
    seen = set()
    unique = []
    for chunk in chunks:
        key = chunk.lower()
        if key in _PROMPT_JUNK_CHUNKS:
            continue
        if len(key.split()) == 1 and key in {"on", "in", "at", "with", "for", "by"}:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return ", ".join(unique)


def save_texture_prompts_json(texture_prompts: dict, out_dir: Path) -> Path:
    path = out_dir / "texture_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texture_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class HeroPromptStrategy(ABC):
    """Strategy interface for vision prompt construction and prompt post-processing."""

    @property
    @abstractmethod
    def vision_system_prompt(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_texture_prompts(self, visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
        raise NotImplementedError
