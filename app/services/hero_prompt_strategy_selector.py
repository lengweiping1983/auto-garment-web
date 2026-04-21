"""Selector for hero prompt generation strategies."""

from __future__ import annotations

from app.services.hero_prompt_strategy_a import HeroPromptStrategyA
from app.services.hero_prompt_strategy_b import HeroPromptStrategyB
from app.services.hero_prompt_strategy_base import HeroPromptStrategy, validate_hero_prompt_scheme


def get_hero_prompt_strategy(hero_prompt_scheme: str = "b") -> HeroPromptStrategy:
    scheme = validate_hero_prompt_scheme(hero_prompt_scheme)
    if scheme == "a":
        return HeroPromptStrategyA()
    return HeroPromptStrategyB()
