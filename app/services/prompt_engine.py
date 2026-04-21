"""Prompt engine — builds texture_prompts.json from LLM-generated visual_elements.

LLM (VisionService) already returns complete prompts in visual["generated_prompts"].
This module only does: formatting, sanitization, and JSON assembly.
No prompt generation or heavy injection — the LLM already did the work.
"""
import json
from pathlib import Path

try:
    from app.core.prompt_sanitizer import sanitize_prompt, sanitize_prompt_for_image_generation, sanitize_prompts_in_dict, sanitize_blur_risks
except Exception:
    def sanitize_prompt(text, domain="generic", prompt_role="positive"):
        return text
    def sanitize_prompt_for_image_generation(text, prompt_role="positive"):
        return text
    def sanitize_prompts_in_dict(data, keys=("prompt",), domain="generic"):
        return data
    def sanitize_blur_risks(text):
        return text


TEXTURE_NEGATIVE_EN = (
    "no animals, no characters, no faces, no people, no text, "
    "no labels, no captions, no titles, no words, no letters, no typography, no logo, no watermark, "
    "no house, no river, no full landscape scene, no scenery, no environment, no background scene, no poster composition, no sticker sheet, "
    "no harsh black outlines, no dense confetti, no neon colors, no muddy dark colors, "
    "no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no blurred background, "
    "no folds, no wrinkles, no draping, no creases, no shadows, no 3D fabric photography, no light variation across surface, "
    "no gradient backgrounds inside individual panels, no photographic realism, no vector flatness, no digital gradient, "
    "blurry, out of focus, smeared, smudged, vignette, distorted, deformed, low quality, jpeg artifacts, grainy"
)

HERO_NEGATIVE_EN = (
    "text, labels, captions, titles, typography, words, letters, signage, logo, watermark, "
    "colored background, tinted backdrop, gradient background, plain light box, colored background box, filled rectangle, "
    "background art, scenery, landscape, environment, ground plane, floor, border, frame, extra objects, "
    "drop shadow, contact shadow, cast shadow, halo effect around subject, "
    "full illustration scene, poster composition, sticker sheet, garment mockup, fashion model, mannequin, "
    "person wearing garment, product photo, lookbook, vignette, "
    "botanical backdrop, foliage behind subject, painted wash behind subject, garden background, meadow background, "
    "blurry, out of focus, smeared, smudged, distorted, deformed, low quality, jpeg artifacts, grainy"
)


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

        # 3. Sanitize: stop-words, banned words, blur risks
        cleaned = sanitize_prompt(raw, domain="fashion")
        cleaned = sanitize_blur_risks(cleaned)
        cleaned = sanitize_prompt_for_image_generation(cleaned, prompt_role="positive")

        purpose, panel, role, negative = meta[tid]

        item = {
            "texture_id": tid,
            "purpose": purpose,
            "prompt": cleaned,
            "negative_prompt": negative,
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

    # Final safety pass over all prompts + negative_prompts
    texture_prompts = sanitize_prompts_in_dict(
        texture_prompts, keys=("prompt", "negative_prompt"), domain="fashion"
    )

    for item in texture_prompts.get("prompts", []):
        item["prompt"] = sanitize_prompt_for_image_generation(item.get("prompt", ""), prompt_role="positive")

    # Rebuild prompt_map after final sanitization
    prompt_map = {p["texture_id"]: p["prompt"] for p in texture_prompts["prompts"]}
    return prompt_map, texture_prompts


def save_texture_prompts(texture_prompts: dict, out_dir: Path) -> Path:
    path = out_dir / "texture_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texture_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
