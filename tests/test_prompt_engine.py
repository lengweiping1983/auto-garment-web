from pathlib import Path

from app.services.prompt_engine import generate_texture_prompts


def test_hero_prompt_is_forced_to_pure_white_background(tmp_path: Path) -> None:
    visual = {
        "generated_prompts": {
            "hero_motif_1": "centered subject, transparent PNG cutout, real alpha background, no background, clean silhouette",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "tiny accent pattern",
        }
    }

    prompt_map, texture_prompts = generate_texture_prompts(visual, tmp_path)
    hero_prompt = prompt_map["hero_motif_1"].lower()
    hero_entry = next(item for item in texture_prompts["prompts"] if item["texture_id"] == "hero_motif_1")

    assert "pure white background" in hero_prompt
    assert "no shadow" in hero_prompt
    assert "clean crisp edges" in hero_prompt
    assert "transparent" not in hero_prompt
    assert "alpha background" not in hero_prompt
    assert "cutout" not in hero_prompt
    assert hero_entry["purpose"] == "AI生成主图白底定位图案"
