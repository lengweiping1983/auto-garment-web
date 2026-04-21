"""Prompt engine — generates texture prompts and hero prompt from visual_elements.

This module replaces the CLI script `生成设计简报.py`.
It preserves ALL injection logic: family_contract, micro_structure,
palette_constraints, reference_context, hero_edge_contract, etc.
"""
import json
from pathlib import Path

from app.core.prompt_blocks import (
    TEXTURE_NEGATIVE_EN,
    HERO_NEGATIVE_EN,
    build_family_contract_text,
    build_single_texture_prompt_en,
    build_transparent_hero_prompt_en,
)

try:
    from app.core.prompt_sanitizer import sanitize_prompt, sanitize_prompts_in_dict
except Exception:
    def sanitize_prompt(text, domain="generic", prompt_role="positive"):
        return text
    def sanitize_prompts_in_dict(data, keys=("prompt",), domain="generic"):
        return data


def _collect_hero_subjects(visual_dict: dict) -> list[tuple[int, float, str, str]]:
    """Return S/A grade hero-suitable subjects sorted by visual importance."""
    dominant = visual_dict.get("dominant_objects", [])
    candidates = []
    for obj in dominant:
        grade = obj.get("grade", "").upper()
        usage = obj.get("suggested_usage", "")
        if grade in ("S", "A") and usage == "hero_motif":
            name = obj.get("name", "").strip()
            desc = obj.get("description", "").strip()
            form_type = obj.get("geometry", {}).get("form_type", "").strip()
            geo = obj.get("geometry", {})
            ratio = geo.get("canvas_ratio", 0)
            grade_score = 2 if grade == "S" else 1
            if desc:
                label = f"{name}: {desc}" if name else desc
                if form_type:
                    label = f"{label} Form type: {form_type}."
                candidates.append((grade_score, ratio, label, name or desc))
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates


def _enrich_hero_prompt_from_dominant_objects(visual_dict: dict, base_hero_prompt: str) -> str:
    """Extract all S/A grade hero-suitable subjects and prepend a composite brief."""
    candidates = _collect_hero_subjects(visual_dict)
    if not candidates:
        return base_hero_prompt
    subject_detail = "; ".join(c[2] for c in candidates)
    composition_rule = (
        "Composite hero requirement: include every listed hero subject in one cohesive foreground apparel placement graphic. "
        "Preserve the recognizable relative roles from the reference image, keep each subject complete and readable, "
        "arrange them as a balanced compact group suitable for splitting across left and right front garment pieces, "
        "and simplify only minor background clutter. Do not omit any listed hero subject; do not reduce the hero graphic to only one subject. "
        "If the base prompt gives extra detail for one subject, use that as detail for that subject while still drawing the full composite group."
    )
    # Prepend the visual-fact paragraph so Neo AI sees "what to draw" first
    return f"Subject visual facts from reference image: {subject_detail}. {composition_rule} {base_hero_prompt}"


def _inject_micro_structure(prompt_text: str, texture_id: str, micro: dict) -> str:
    """Inject micro-structure parameters into prompt."""
    if not micro or texture_id not in micro:
        return prompt_text
    info = micro.get(texture_id, {})
    parts = []
    scale = info.get("motif_scale_relative", "")
    if scale:
        parts.append(f"motif scale: {scale}")
    count = info.get("motif_count_per_tile", "")
    if count:
        parts.append(f"density: {count}")
    ns = info.get("negative_space_ratio", "")
    if ns:
        parts.append(f"negative space: {ns}")
    desc = info.get("repeat_unit_description", "")
    if desc:
        parts.append(f"repeat unit: {desc}")
    mix = info.get("element_type_mix", {})
    if mix:
        mix_str = ", ".join(f"{k} {int(v*100)}%" for k, v in mix.items())
        parts.append(f"element mix: {mix_str}")
    if not parts:
        return prompt_text
    return f"{prompt_text}, micro-structure contract: {', '.join(parts)}"


def _inject_palette_constraints(prompt_text: str, texture_id: str, palette: dict) -> str:
    """Append hex color constraints to reduce AI color drift."""
    if not palette:
        return prompt_text
    primary = palette.get("primary", [])
    secondary = palette.get("secondary", [])
    accent = palette.get("accent", [])
    constraints = []
    if texture_id == "main" and primary:
        constraints.append(
            f"ground color must be exactly {primary[0]}, keep a visible repeat pattern with concrete small motifs, "
            "no abstract wash, no plain color wash, no plain texture, no paper grain only, no gradient, no empty background, "
            "no tonal atmosphere only, no blurred background, no figurative elements, no scene, no landscape"
        )
    elif texture_id == "secondary" and secondary:
        constraints.append(
            f"light ground and pattern tones must stay within {secondary[0]} family, keep a visible repeat pattern with concrete small motifs or lattice, "
            "no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no warm cast, no scene"
        )
    elif texture_id == "accent_light" and (accent or primary):
        c = accent[0] if accent else primary[0]
        constraints.append(f"scattered accent elements must use {c} tones only")
    elif texture_id == "hero_motif_1" and primary:
        bg = primary[0] if primary else "#ffffff"
        fg = accent[0] if accent else (secondary[0] if secondary else bg)
        constraints.append(
            f"transparent alpha background only, preserve the user's main reference subject as much as possible, "
            f"isolated foreground subject painted in {fg} tones while keeping recognizable source-image silhouette and key details, "
            "complete uncropped subject with full head and hair visible, empty transparent pixels above and around the subject, "
            "soft fading edges, no checkerboard transparency preview, no fake transparency grid, no colored background box, "
            "no garden, no foliage behind subject, no botanical backdrop, no rectangular composition, no full illustration scene"
        )
    if constraints:
        return f"{prompt_text}, color constraint: {', '.join(constraints)}"
    return prompt_text


def _force_transparent_motif_prompt(prompt_text: str, motif_id: str = "") -> str:
    """Ensure hero motif prompt enforces transparent cutout format."""
    required = (
        "isolated foreground motif only, transparent PNG cutout, real alpha background, "
        "empty transparent pixels around the subject, no background, no background art, "
        "no plain light background, no plain warm background, no colored background box, "
        "no filled rectangular background, no checkerboard transparency preview, no fake transparency grid, "
        "no scenery, no semi-transparent full-image patch"
    )
    hero_required = (
        "hero_motif_1 must preserve and recreate the primary subject from the user's reference image as much as possible, "
        "people, faces, characters, animals, products, icons, objects, or logos are allowed if they are the user's main image content, "
        "keep the recognizable silhouette, color identity, pose, proportions, and key visual details, "
        "hero_motif_1 must be foreground subject only, no scene, no garden, "
        "no meadow, no landscape, no environment, no foliage behind subject, "
        "no botanical backdrop, no painted wash behind subject, no vignette, "
        "no rectangular composition, no full illustration scene, no checkerboard transparency preview, "
        "no fake transparency grid, no ground shadow"
    )
    text = prompt_text.strip()
    for old in (
        "plain light background", "plain warm background", "removable plain background",
        "removable plain backgrounds", "suitable for background removal",
        "full illustration scene", "rectangular composition", "botanical backdrop",
        "foliage behind subject", "painted wash behind subject", "garden background", "background art",
    ):
        text = text.replace(old, "transparent alpha background")
    text = text.replace("as as possible", "as much as possible")
    lower = text.lower()
    suffix = required
    if motif_id == "hero_motif_1":
        suffix = f"{required}, {hero_required}"
    if "transparent png cutout" in lower and "real alpha background" in lower:
        if motif_id == "hero_motif_1":
            return f"{text}, no colored background box, no semi-transparent full-image patch, {hero_required}"
        return f"{text}, isolated foreground motif only, empty transparent pixels around the subject, no colored background box, no scenery, no semi-transparent full-image patch"
    return f"{text}, {suffix}"


def generate_texture_prompts(visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
    """Generate full texture_prompts.json from visual_elements dict.

    Returns:
        prompt_map: {texture_id: final_prompt_text}
        texture_prompts_payload: dict ready to be saved as texture_prompts.json
    """
    palette = visual.get("palette", {})
    style = visual.get("style", {})
    generated_prompts = visual.get("generated_prompts", {})
    design_dna = visual.get("design_dna", {})
    single_texture_derivation = visual.get("single_texture_derivation", {})
    texture_micro_structure = visual.get("texture_micro_structure", {})
    hero_edge_contract = visual.get("hero_edge_contract", {})
    theme_to_piece_strategy = visual.get("theme_to_piece_strategy", {})

    family_contract = build_family_contract_text(
        style=style,
        palette=palette if isinstance(palette, dict) else {},
        design_dna=design_dna,
    )

    # Base prompts from generated_prompts or fallback
    motif_str = ", ".join(design_dna.get("motif_vocabulary", [])[:3])
    medium = style.get("medium", "watercolor") if style else "watercolor"
    mood = style.get("mood", "quiet and elegant") if style else "quiet and elegant"

    base_guard = (
        "commercial apparel repeat, only atmosphere and color from the theme, no large figurative subject, "
        "no mushroom or animal as full-body hero, no complete scene, no landscape, no scenery, no environment, no poster composition, cohesive with all other panels, "
        "must contain concrete visible repeat elements, no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only"
    )

    main_prompt = generated_prompts.get("main", f"seamless tileable visible repeat pattern on pale ground, concrete small botanical or geometric motifs inspired by {motif_str}, stable low-to-medium density, clear repeated elements, commercial apparel base fabric, abundant breathing room, same {medium} brush style, no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no blurred background, no figurative subject, no flower bouquet, no landscape scene, no environment, no scenery, {base_guard}, no text")
    secondary_prompt = generated_prompts.get("secondary", f"seamless tileable coordinating visible repeat pattern, soft light ground with concrete small motifs, lattice, linework, leaves, dots, or controlled geometric elements inspired by {motif_str}, medium density but airy, same {medium} brush style, stable repeat structure, no standalone scene, no environment, no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, {base_guard}, no text")
    accent_prompt = generated_prompts.get("accent_light", generated_prompts.get("accent", f"seamless tileable small-scale accent pattern, tiny scattered elements inspired by {motif_str}, very small scale repeating, charming but controlled density, same palette and brush as main panel, no standalone scene, no text"))

    motif_guard = "isolated foreground motif only, transparent PNG cutout, real alpha background, no background, no checkerboard transparency preview, no fake transparency grid, no plain-color box, no filled rectangular background, no scenery, no semi-transparent full-image patch"
    hero_source_guard = "preserve and recreate the primary subject from the user's reference image as much as possible, people, faces, characters, animals, products, icons, objects, or logos are allowed if they are the user's main image content, keep the recognizable silhouette, color identity, pose, proportions, and key visual details, complete uncropped subject, full head and hair visible, generous transparent margin above and around the subject"
    hero_guard = f"{hero_source_guard}, {motif_guard}, no garden, no meadow, no landscape, no environment, no foliage behind subject, no botanical backdrop, no painted wash behind subject, no rectangular composition, no full illustration scene, no vignette, no ground shadow"
    # Enrich hero prompt from all S/A grade dominant objects (do not pick just one)
    raw_hero = generated_prompts.get("hero_motif_1", generated_prompts.get("hero_motif", f"isolated foreground hero motif only, centered subject, transparent PNG cutout with real alpha background, {hero_source_guard}, empty transparent pixels around the subject, soft clean edges, balanced negative space, {medium} hand-painted placement print element, {hero_guard}, no text"))
    raw_hero = _enrich_hero_prompt_from_dominant_objects(visual, raw_hero)

    # When multiple S/A hero subjects exist, update theme strategy to reflect composite requirement
    hero_subjects = _collect_hero_subjects(visual)
    if isinstance(theme_to_piece_strategy, dict) and len(hero_subjects) > 1:
        subject_names = [c[3] for c in hero_subjects]
        theme_to_piece_strategy = dict(theme_to_piece_strategy)
        theme_to_piece_strategy["hero_motif"] = (
            "组合主卖点定位图案：保留并组合 "
            + "、".join(subject_names)
            + "，形成一个可前片定位的透明主图，不做三选一。"
        )

    hero_motif_1_prompt = _force_transparent_motif_prompt(raw_hero, "hero_motif_1")

    # Inject hero_edge_contract
    if hero_edge_contract:
        min_margin = hero_edge_contract.get("min_margin_ratio", 0.30)
        fade = hero_edge_contract.get("edge_fade_pixels", "")
        alpha_behavior = hero_edge_contract.get("required_alpha_behavior", "")
        forbidden = hero_edge_contract.get("forbidden_alpha_patterns", [])
        edge_bits = [f"minimum {int(min_margin * 100)}% transparent margin around subject"]
        if fade:
            edge_bits.append(f"edge fade: {fade}")
        if alpha_behavior:
            edge_bits.append(f"alpha behavior: {alpha_behavior}")
        if forbidden:
            edge_bits.append(f"forbidden: {', '.join(forbidden)}")
        hero_motif_1_prompt = f"{hero_motif_1_prompt}, edge contract: {', '.join(edge_bits)}"

    def _reference_context(texture_id: str, prompt_text: str) -> str:
        dna_bits = []
        if design_dna:
            for key in ("fusion_rule", "linework", "brushwork", "material_feel", "negative_space"):
                value = design_dna.get(key)
                if value:
                    dna_bits.append(f"{key}: {value}")
            motifs_from_dna = design_dna.get("motif_vocabulary")
            if motifs_from_dna:
                dna_bits.append(f"motif vocabulary: {', '.join(str(v) for v in motifs_from_dna[:8])}")
        derivation = ""
        if isinstance(single_texture_derivation, dict):
            derivation = single_texture_derivation.get(texture_id, "")
        context = (
            "Use reference image 1 as the source for palette, brush language, material feel, small supporting motifs, and user intent; "
            "the texture must coordinate organically with hero_motif_1 and must not look pasted from a different artwork. "
        )
        if derivation:
            context += f"Texture derivation from reference image: {derivation}. "
        if dna_bits:
            context += f"Shared design DNA: {'; '.join(dna_bits)}. "
        return f"{context}{prompt_text}"

    texture_ids = ["hero_motif_1", "main", "secondary", "accent_light"]
    prompts_data = [
        ("hero_motif_1", "AI生成主图透明定位图案", hero_motif_1_prompt, "single_hero", "placement_motif"),
        ("main", "可穿大身裁片", _reference_context("main", _inject_micro_structure(main_prompt, "main", texture_micro_structure)), "single_texture", "base_texture"),
        ("secondary", "协调大副裁片", _reference_context("secondary", _inject_micro_structure(secondary_prompt, "secondary", texture_micro_structure)), "single_texture", "base_texture"),
        ("accent_light", "小面板与受控点缀", _reference_context("accent_light", _inject_micro_structure(accent_prompt, "accent_light", texture_micro_structure)), "single_texture", "accent_texture"),
    ]

    def _make_prompt(texture_id, purpose, prompt_text, panel, role):
        negative = HERO_NEGATIVE_EN if role == "placement_motif" else TEXTURE_NEGATIVE_EN
        item = {
            "texture_id": texture_id,
            "purpose": purpose,
            "prompt": sanitize_prompt(_inject_palette_constraints(prompt_text, texture_id, palette), domain="fashion"),
            "negative_prompt": negative,
        }
        if panel:
            item["panel"] = panel
        if role:
            item["role"] = role
        return item

    prompts = [
        _make_prompt(tid, purpose, ptext, panel, role)
        for tid, purpose, ptext, panel, role in prompts_data
    ]

    texture_prompts = {
        "style_id": f"auto_garment_commercial_v1",
        "generation_owner": "neo_ai",
        "family_contract": family_contract,
        "prompts": prompts,
    }
    # 过滤所有正向/负向 prompt 中的停用词和可能触发生图安全过滤的词
    texture_prompts = sanitize_prompts_in_dict(texture_prompts, keys=("prompt", "negative_prompt"), domain="fashion")

    prompt_map = {p["texture_id"]: p["prompt"] for p in prompts}
    return prompt_map, texture_prompts


def save_texture_prompts(texture_prompts: dict, out_dir: Path) -> Path:
    path = out_dir / "texture_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texture_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
