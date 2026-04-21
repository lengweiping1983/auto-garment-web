"""Prompt engine — delegates hero prompt generation to A/B strategies."""

from __future__ import annotations

from pathlib import Path

from app.services.hero_prompt_strategy_base import save_texture_prompts_json
from app.services.hero_prompt_strategy_selector import get_hero_prompt_strategy


def generate_texture_prompts(
    visual: dict,
    out_dir: Path,
    hero_prompt_scheme: str = "b",
) -> tuple[dict[str, str], dict]:
    strategy = get_hero_prompt_strategy(hero_prompt_scheme)
    return strategy.generate_texture_prompts(visual, out_dir)


def save_texture_prompts(texture_prompts: dict, out_dir: Path) -> Path:
    return save_texture_prompts_json(texture_prompts, out_dir)
