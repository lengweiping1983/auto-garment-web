"""Prompt engine — builds texture_prompts.json from LLM-generated visual_elements.

LLM (VisionService) already returns complete prompts in visual["generated_prompts"].
This module only does: formatting, sanitization, and JSON assembly.
No prompt generation or heavy injection — the LLM already did the work.
"""
import json
import re
from pathlib import Path

try:
    from app.core.prompt_sanitizer import prepare_image_generation_payload
except Exception:
    def prepare_image_generation_payload(prompt, negative_prompt="", strict=False):
        return prompt, negative_prompt

from app.core.prompt_blocks import HERO_NEGATIVE_EN, PANEL_DEFAULTS_EN, TEXTURE_NEGATIVE_EN


def _ensure_white_background_hero(prompt: str) -> str:
    """Fallback: force pure-white-background constraints if LLM missed them."""
    if not prompt:
        return prompt
    replacements = {
        "transparent png cutout": "pure white background",
        "transparent background": "pure white background",
        "transparent alpha background": "pure white background",
        "alpha background": "pure white background",
        "real alpha background": "pure white background",
        "transparent margin": "clean white margin",
        "background removal": "pure white background",
        "checkerboard transparency preview": "pure white background",
        "fake transparency grid": "pure white background",
        "no background": "pure white background",
        "cutout": "clean edges",
    }
    cleaned = prompt
    for bad, good in replacements.items():
        cleaned = cleaned.replace(bad, good)
        cleaned = cleaned.replace(bad.title(), good)
        cleaned = cleaned.replace(bad.upper(), good.upper())
    for bad in (
        "plain light background",
        "plain warm background",
        "removable plain background",
        "removable plain backgrounds",
        "suitable for background removal",
        "transparent",
        "alpha",
    ):
        cleaned = cleaned.replace(bad, "pure white background")
    lower = cleaned.lower()
    if "pure white background" in lower and "no shadow" in lower and "clean" in lower and "edge" in lower:
        return cleaned
    suffix = (
        "isolated foreground subject only, pure white background, no shadow, "
        "no floor, no scenery, no extra objects, clean crisp edges, full uncropped figure"
    )
    return f"{cleaned}, {suffix}"


_PANEL_CONTRADICTION_PATTERNS = {
    "hero_motif_1": (
        r"\bseamless\b",
        r"\btileable\b",
        r"\ball-over print\b",
        r"\brepeat(?: pattern)?\b",
        r"\bfabric texture\b",
        r"\bpattern swatch\b",
        r"\btextile print\b",
    ),
    "texture_1": (
        r"\bmodel\b",
        r"\bmannequin\b",
        r"\bperson\b",
        r"\bwearing garment\b",
        r"\bgarment mockup\b",
        r"\bt-?shirt mockup\b",
        r"\bplacement graphic\b",
        r"\bcentered complete subject\b",
        r"\bfull uncropped figure\b",
        r"\bpure white background\b",
    ),
    "texture_2": (
        r"\bmodel\b",
        r"\bmannequin\b",
        r"\bperson\b",
        r"\bwearing garment\b",
        r"\bgarment mockup\b",
        r"\bt-?shirt mockup\b",
        r"\bplacement graphic\b",
        r"\bcentered complete subject\b",
        r"\bfull uncropped figure\b",
        r"\bpure white background\b",
    ),
    "texture_3": (
        r"\bmodel\b",
        r"\bmannequin\b",
        r"\bperson\b",
        r"\bwearing garment\b",
        r"\bgarment mockup\b",
        r"\bt-?shirt mockup\b",
        r"\bplacement graphic\b",
        r"\bcentered complete subject\b",
        r"\bfull uncropped figure\b",
        r"\bpure white background\b",
    ),
}

_PROMPT_JUNK_CHUNKS = {
    "on",
    "in",
    "at",
    "with",
    "feeling",
    "mockup feeling",
    "garment mockup feeling",
}


def _clean_prompt_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"([,.;:!?]){2,}", r"\1", text)
    return text.strip(" ,;")


def _dedupe_prompt_chunks(text: str) -> str:
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


def _merge_panel_prompt(raw: str, panel_id: str) -> str:
    text = raw or ""

    for pattern in _PANEL_CONTRADICTION_PATTERNS.get(panel_id, ()):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    base_contract = PANEL_DEFAULTS_EN.get(panel_id, "")
    if base_contract:
        text = f"{text}, {base_contract}" if text else base_contract

    return _dedupe_prompt_chunks(_clean_prompt_text(text))

def generate_texture_prompts(visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
    """Build texture prompts from LLM-generated visual elements."""
    generated_prompts = visual.get("generated_prompts", {})

    # Texture IDs we expect from the LLM
    texture_ids = ["hero_motif_1", "texture_1", "texture_2", "texture_3"]

    # Map texture_id → (purpose, panel, role, negative)
    meta = {
        "hero_motif_1": ("AI生成主图白底定位图案",   "single_hero", "hero_motif_1", HERO_NEGATIVE_EN),
        "texture_1":    ("纹理1",                  "single_texture", "base_texture",   TEXTURE_NEGATIVE_EN),
        "texture_2":    ("纹理2",                  "single_texture", "base_texture",   TEXTURE_NEGATIVE_EN),
        "texture_3":    ("纹理3",                  "single_texture", "base_texture",   TEXTURE_NEGATIVE_EN),
    }

    prompts: list[dict] = []
    prompt_map: dict[str, str] = {}

    for tid in texture_ids:
        # 1. Get LLM prompt; warn if missing (should never happen with good LLM)
        raw = generated_prompts.get(tid, "")
        if not raw:
            print(f"[WARN] LLM did not return prompt for {tid}, using empty string")

        # 2. Program fallback: ensure hero has pure white background
        if tid == "hero_motif_1":
            raw = _ensure_white_background_hero(raw)
        raw = _merge_panel_prompt(raw, tid)

        purpose, panel, role, negative = meta[tid]
        cleaned, cleaned_negative = prepare_image_generation_payload(raw, negative, strict=False)

        item = {
            "texture_id": tid,
            "purpose": purpose,
            "prompt": cleaned,
            "negative_prompt": cleaned_negative,
            "panel": panel,
            "role": role,
        }
        prompts.append(item)
        prompt_map[tid] = cleaned


    texture_prompts = {
        "style_id": "auto_garment_commercial_v1",
        "generation_owner": "neo_ai",
        "prompts": prompts,
    }
    for item in texture_prompts.get("prompts", []):
        item["prompt"], item["negative_prompt"] = prepare_image_generation_payload(
            item.get("prompt", ""),
            item.get("negative_prompt", ""),
            strict=False,
        )

    prompt_map = {p["texture_id"]: p["prompt"] for p in texture_prompts["prompts"]}
    return prompt_map, texture_prompts


def save_texture_prompts(texture_prompts: dict, out_dir: Path) -> Path:
    path = out_dir / "texture_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texture_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
