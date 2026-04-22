from pathlib import Path

import pytest

from app.services.prompt_engine import generate_texture_prompts
from app.services.hero_prompt_strategy_selector import get_hero_prompt_strategy


def test_hero_prompt_default_is_scheme_b(tmp_path: Path) -> None:
    visual = {
        "dominant_objects": [
            {
                "name": "girl",
                "grade": "S",
                "description": "pink dress facing front",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.42, "form_type": "character"},
            }
        ],
        "generated_prompts": {
            "hero_motif_1": "centered subject, transparent PNG cutout, real alpha background, no background, clean silhouette",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "small accent pattern",
        }
    }

    prompt_map, texture_prompts = generate_texture_prompts(visual, tmp_path)
    hero_prompt = prompt_map["hero_motif_1"].lower()
    hero_entry = next(item for item in texture_prompts["prompts"] if item["texture_id"] == "hero_motif_1")

    assert "pure white background" in hero_prompt
    assert "centered complete subject" in hero_prompt
    assert "apparel placement graphic" in hero_prompt
    assert "transparent png cutout" not in hero_prompt
    assert "real alpha background" not in hero_prompt
    assert hero_entry["purpose"] == "AI生成主图白底图"


def test_hero_prompt_scheme_a_keeps_pure_white_background(tmp_path: Path) -> None:
    visual = {
        "generated_prompts": {
            "hero_motif_1": "centered subject, transparent PNG cutout, real alpha background, no background, clean silhouette",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "small accent pattern",
        }
    }

    prompt_map, texture_prompts = generate_texture_prompts(visual, tmp_path, hero_prompt_scheme="a")
    hero_prompt = prompt_map["hero_motif_1"].lower()
    hero_entry = next(item for item in texture_prompts["prompts"] if item["texture_id"] == "hero_motif_1")

    assert "pure white background" in hero_prompt
    assert "no shadow" in hero_prompt
    assert "clean crisp edges" in hero_prompt
    assert "transparent" not in hero_prompt
    assert "alpha background" not in hero_prompt
    assert "cutout" not in hero_prompt
    assert hero_entry["purpose"] == "AI生成主图白底定位图案"


def test_hero_prompt_scheme_b_uses_white_background_and_keeps_a_textures(tmp_path: Path) -> None:
    visual = {
        "dominant_objects": [
            {
                "name": "girl",
                "grade": "S",
                "description": "pink dress facing front",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.42, "form_type": "character"},
            },
            {
                "name": "rabbit",
                "grade": "A",
                "description": "small rabbit at left side",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.18, "form_type": "animal"},
            },
        ],
        "hero_edge_contract": {
            "min_margin_ratio": 0.30,
            "edge_fade_pixels": "2-6px soft anti-aliased edge only",
            "required_alpha_behavior": "hard binary alpha inside subject silhouette",
            "forbidden_alpha_patterns": ["gradient wash fade to transparent", "colored fringe on edge"],
        },
        "generated_prompts": {
            "hero_motif_1": "centered complete subject, pure white background, clean crisp edges",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "small accent pattern",
        },
    }

    prompt_map, texture_prompts = generate_texture_prompts(visual, tmp_path, hero_prompt_scheme="b")
    hero_prompt = prompt_map["hero_motif_1"].lower()
    hero_entry = next(item for item in texture_prompts["prompts"] if item["texture_id"] == "hero_motif_1")
    texture_1_prompt = prompt_map["texture_1"].lower()

    assert "pure white background" in hero_prompt
    assert "centered complete subject" in hero_prompt
    assert "apparel placement graphic" in hero_prompt
    assert "composite hero requirement" in hero_prompt
    assert "balanced separated group" in hero_prompt
    assert "moderate spacing" in hero_prompt
    assert "visible white breathing room" in hero_prompt
    assert "do not let subjects touch, overlap, merge, or share outer contours" in hero_prompt
    assert "individually readable and individually extractable" in hero_prompt
    assert "compact cluster" in hero_prompt
    assert "balanced compact group" not in hero_prompt
    assert "girl" in hero_prompt and "rabbit" in hero_prompt
    assert "transparent png cutout" not in hero_prompt
    assert "real alpha background" not in hero_prompt
    assert "checkerboard transparency preview" not in hero_prompt
    assert "fake transparency grid" not in hero_prompt
    assert "edge contract" not in hero_prompt
    assert hero_entry["purpose"] == "AI生成主图白底图"

    assert "seamless repeat floral pattern" in texture_1_prompt
    assert "seamless tileable visible repeat pattern" in texture_1_prompt
    assert "transparent png cutout" not in texture_1_prompt


def test_scheme_b_ignores_legacy_hero_edge_contract_when_building_white_hero(tmp_path: Path) -> None:
    visual = {
        "dominant_objects": [
            {
                "name": "bird",
                "grade": "S",
                "description": "glass bird facing left",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.33, "form_type": "animal"},
            }
        ],
        "hero_edge_contract": {
            "min_margin_ratio": 0.30,
            "edge_fade_pixels": "2-6px soft anti-aliased edge only",
            "required_alpha_behavior": "hard binary alpha inside subject silhouette",
            "forbidden_alpha_patterns": ["gradient wash fade to transparent", "colored fringe on edge"],
        },
        "generated_prompts": {
            "hero_motif_1": "transparent PNG cutout bird, real alpha background, no background",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "small accent pattern",
        },
    }

    prompt_map, _ = generate_texture_prompts(visual, tmp_path, hero_prompt_scheme="b")
    hero_prompt = prompt_map["hero_motif_1"].lower()

    assert "pure white background" in hero_prompt
    assert "transparent png cutout" not in hero_prompt
    assert "real alpha background" not in hero_prompt
    assert "edge contract" not in hero_prompt
    assert "minimum 30% transparent margin" not in hero_prompt


def test_scheme_b_many_subjects_keep_all_subjects_separated_for_cutout(tmp_path: Path) -> None:
    visual = {
        "dominant_objects": [
            {
                "name": "girl",
                "grade": "S",
                "description": "pink dress facing front",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.42, "form_type": "character"},
            },
            {
                "name": "rabbit",
                "grade": "A",
                "description": "small rabbit at left side",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.18, "form_type": "animal"},
            },
            {
                "name": "bird",
                "grade": "A",
                "description": "small bird at upper right",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.14, "form_type": "animal"},
            },
            {
                "name": "flower",
                "grade": "A",
                "description": "large flower near the bottom",
                "suggested_usage": "hero_motif",
                "geometry": {"canvas_ratio": 0.16, "form_type": "botanical"},
            },
        ],
        "generated_prompts": {
            "hero_motif_1": "centered complete subject, pure white background, clean crisp edges",
            "texture_1": "seamless repeat floral pattern",
            "texture_2": "coordinated seamless dots",
            "texture_3": "small accent pattern",
        },
        "theme_to_piece_strategy": {
            "hero_motif": "旧描述"
        },
    }

    prompt_map, _ = generate_texture_prompts(visual, tmp_path, hero_prompt_scheme="b")
    hero_prompt = prompt_map["hero_motif_1"].lower()
    strategy = visual["theme_to_piece_strategy"]["hero_motif"]

    assert "girl" in hero_prompt
    assert "rabbit" in hero_prompt
    assert "bird" in hero_prompt
    assert "flower" in hero_prompt
    assert "do not omit any listed hero subject" in hero_prompt
    assert "do not reduce the hero graphic to only one subject" in hero_prompt
    assert "scale subjects slightly smaller to preserve separation" in hero_prompt
    assert "touch, overlap, merge, or share outer contours" in hero_prompt
    assert "visible white breathing room" in hero_prompt
    assert strategy == "旧描述"


def test_texture_prompts_strip_text_and_blur_risks_without_relying_on_negative_prompt(tmp_path: Path) -> None:
    visual = {
        "generated_prompts": {
            "hero_motif_1": "clean hero subject",
            "texture_1": "dreamy hazy seamless floral repeat with handwritten text, logo, soft focus, bokeh, washed out pastel look",
            "texture_2": "misty geometric pattern with decorative letters and shallow depth of field",
            "texture_3": "fuzzy micro pattern with typography and watermark",
        }
    }

    prompt_map, texture_prompts = generate_texture_prompts(visual, tmp_path, hero_prompt_scheme="b")
    texture_1_prompt = prompt_map["texture_1"].lower()
    texture_2_prompt = prompt_map["texture_2"].lower()
    texture_3_prompt = prompt_map["texture_3"].lower()
    texture_1_entry = next(item for item in texture_prompts["prompts"] if item["texture_id"] == "texture_1")

    assert "dreamy" not in texture_1_prompt
    assert "hazy" not in texture_1_prompt
    assert "with handwritten text" not in texture_1_prompt
    assert ", logo" not in texture_1_prompt
    assert ", watermark" not in texture_3_prompt
    assert "decorative letters" not in texture_2_prompt
    assert "typography and watermark" not in texture_3_prompt
    assert "no soft focus" in texture_1_prompt
    assert "no logo" in texture_1_prompt
    assert "no watermark" in texture_3_prompt
    assert "crisp clean repeat edges" in texture_1_prompt
    assert "sharp motif boundaries" in texture_1_prompt
    assert "high print legibility" in texture_3_prompt
    assert texture_1_entry["negative_prompt"], "negative prompt may still exist, but positive prompt must already be hardened"


def test_invalid_hero_prompt_scheme_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported hero_prompt_scheme"):
        generate_texture_prompts({"generated_prompts": {}}, tmp_path, hero_prompt_scheme="nope")


def test_scheme_b_vision_prompt_includes_skill_schema_requirements() -> None:
    prompt = get_hero_prompt_strategy("b").vision_system_prompt
    assert "`struct`" not in prompt
    assert "theme_to_piece_strategy" in prompt
    assert "hero_edge_contract" in prompt
    assert "dominant_objects" in prompt
    assert "subject_identity" in prompt
    assert "pure white background" in prompt
    assert "hero_motif_1` 必须是前景主体白底图" in prompt
    assert "balanced separated group" in prompt
    assert "moderate spacing / visible white gap / breathing room" in prompt
    assert "touching / overlap / merged silhouette / shared outer contour" in prompt
