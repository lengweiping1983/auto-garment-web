"""Prompt engine — builds texture_prompts.json from LLM-generated visual_elements.

LLM (VisionService) already returns complete prompts in visual["generated_prompts"].
This module only does: formatting, sanitization, and JSON assembly.
No prompt generation or heavy injection — the LLM already did the work.
"""
import json
from pathlib import Path

try:
    from app.core.prompt_sanitizer import sanitize_prompt, sanitize_prompts_in_dict, sanitize_blur_risks
except Exception:
    def sanitize_prompt(text, domain="generic", prompt_role="positive"):
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
    "plain light box, colored background box, filled rectangle, background art, scenery, landscape, environment, "
    "checkerboard transparency preview, fake transparency grid, semi-transparent full-image patch, "
    "gradient wash fade to transparent, colored fringe on edge, halo effect around subject, "
    "full illustration scene, poster composition, sticker sheet, garment mockup, fashion model, mannequin, "
    "person wearing garment, product photo, lookbook, ground shadow, vignette, "
    "botanical backdrop, foliage behind subject, painted wash behind subject, garden background, meadow background, "
    "blurry, out of focus, smeared, smudged, distorted, deformed, low quality, jpeg artifacts, grainy"
)


def _ensure_transparent_hero(prompt: str) -> str:
    """Fallback: force transparent-background constraints if LLM missed them."""
    if not prompt:
        return prompt
    lower = prompt.lower()
    # Check if already contains key transparency markers
    has_transparent = "transparent" in lower
    has_alpha = "alpha background" in lower or "real alpha" in lower
    has_isolated = "isolated" in lower
    has_no_bg = "no background" in lower
    if has_transparent and has_alpha and has_isolated and has_no_bg:
        return prompt
    # LLM missed some — append mandatory transparency suffix
    suffix = (
        "isolated foreground motif only, transparent PNG cutout, real alpha background, "
        "no background, no checkerboard transparency preview, no fake transparency grid, "
        "no colored rectangle, no plain light box"
    )
    # Remove any existing conflicting phrases first
    for bad in (
        "plain light background", "plain warm background", "removable plain background",
        "removable plain backgrounds", "suitable for background removal",
    ):
        prompt = prompt.replace(bad, "transparent alpha background")
    return f"{prompt}, {suffix}"

def generate_texture_prompts(visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
    """Build texture prompts from LLM-generated visual elements."""
    generated_prompts = visual.get("generated_prompts", {})

    # Texture IDs we expect from the LLM
    texture_ids = ["hero_motif_1", "texture_1", "texture_2", "texture_3"]

    # Map texture_id → (purpose, panel, role, negative)
    meta = {
        "hero_motif_1": ("AI生成主图透明定位图案",   "single_hero", "hero_motif_1", HERO_NEGATIVE_EN),
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

        # 2. Program fallback: ensure hero has transparent background
        if tid == "hero_motif_1":
            raw = _ensure_transparent_hero(raw)

        # 3. Sanitize: stop-words, banned words, blur risks
        cleaned = sanitize_prompt(raw, domain="fashion")
        cleaned = sanitize_blur_risks(cleaned)

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

    # Rebuild prompt_map after final sanitization
    prompt_map = {p["texture_id"]: p["prompt"] for p in texture_prompts["prompts"]}
    return prompt_map, texture_prompts


def save_texture_prompts(texture_prompts: dict, out_dir: Path) -> Path:
    path = out_dir / "texture_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texture_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
