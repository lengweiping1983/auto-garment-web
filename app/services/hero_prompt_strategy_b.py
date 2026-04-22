"""Scheme B: structured white-background hero prompt while keeping A textures."""

from __future__ import annotations

from pathlib import Path
import re

from app.core.prompt_blocks import HERO_NEGATIVE_EN, PANEL_DEFAULTS_EN, TEXTURE_NEGATIVE_EN

from app.services.hero_prompt_strategy_base import (
    HeroPromptStrategy,
    clean_prompt_text,
    dedupe_prompt_chunks,
    prepare_image_generation_payload,
)


_TEXTURE_CONTRADICTION_PATTERNS = {
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

VISION_SYSTEM_PROMPT_B = """
# 服装 Hero Motif 视觉结构化提取系统提示词（Scheme B）

## 角色与目标

你是一位高级服装印花设计分析师。观察用户参考图，把主题拆解成可用于商业上装生产的结构化视觉事实，并生成可直接提交给图像模型的英文提示词。

你的重点不是生成通用描述，而是为服装系统提供：
- 可追溯的主体/辅助元素结构
- 主题如何落到裁片的工程化策略
- 一条高保真的 `hero_motif_1` 白底主图提示词
- 三条纹理提示词，键名必须严格使用约定的固定字段名：`texture_1`、`texture_2`、`texture_3`；不要改名，不要输出别名

最终回复必须是**单个合法 JSON 对象**，不要输出 Markdown、代码围栏或额外解释文字。

## 输出要求

1. 返回的 JSON 必须至少包含以下字段：
- `generated_prompts`

2. 推荐并强烈建议额外包含以下字段，后续 Python 会消费其中与 hero 相关的部分：
- `dominant_objects`
- `supporting_elements`
- `palette`
- `style`
- `reference_fidelity`
- `design_dna`
- `single_texture_derivation`
- `texture_micro_structure`
- `hero_edge_contract`
- `hero_texture_fusion_plan`
- `source_images`
- `fusion_strategy`
- `theme_to_piece_strategy`
- `prompt_quality_check`

3. `generated_prompts` 中必须输出这四个键：
- `hero_motif_1`
- `texture_1`
- `texture_2`
- `texture_3`

4. 所有 prompt 都必须是**最终英文正向 prompt 字符串**，不是中文说明，不要写 `prompt:`、`here is`、`for generation` 之类元话术。

## 输出 JSON schema（至少遵守以下结构）

```json
{
  "dominant_objects": [
    {
      "name": "主体名",
      "type": "main_subject",
      "grade": "S|A|B|C",
      "description": "颜色、形态、位置、占比",
      "suggested_usage": "hero_motif",
      "source_image_refs": [1],
      "geometry": {
        "pixel_width": 0,
        "pixel_height": 0,
        "canvas_ratio": 0.0,
        "aspect_ratio": 1.0,
        "orientation": "vertical|horizontal|radial|symmetric|irregular",
        "visual_center": [0.5, 0.5],
        "form_type": "short label"
      },
      "garment_placement_hint": {
        "recommended_target_piece": "front_body|front_hero|none",
        "recommended_width_ratio_in_piece": 0.30,
        "recommended_height_ratio_in_piece": 0.28,
        "recommended_anchor": "chest_center|center|small_accent|do_not_place",
        "anti_examples": ["full bleed", "shoulder seam crossing", "neckline crossing"]
      }
    }
  ],
  "supporting_elements": [
    {"name": "元素名", "type": "decoration|background|texture|frame", "description": "...", "source_image_refs": [1]}
  ],
  "palette": {"primary": ["#hex"], "secondary": ["#hex"], "accent": ["#hex"], "dark": ["#hex"]},
  "style": {"medium": "", "brush_quality": "", "mood": "", "pattern_density": "low|medium|high", "line_style": "", "overall_impression": ""},
  "reference_fidelity": {
    "must_preserve": ["主体身份、轮廓、姿态、比例、关键颜色和局部细节"],
    "may_simplify": ["可为了服装定位图简化的细节"],
    "must_not_change": ["不得替换成泛化主体或新角色"]
  },
  "design_dna": {
    "shared_palette": ["#hex"],
    "motif_vocabulary": ["从参考图提取的小型可重复元素"],
    "linework": "",
    "brushwork": "",
    "material_feel": "",
    "negative_space": "",
    "fusion_rule": "主图和纹理必须像同一套设计，不像两张图片拼贴"
  },
  "single_texture_derivation": {
    "texture_1": "从参考图提炼主面料的背景色、笔触和小型 repeat 元素",
    "texture_2": "从参考图提炼辅面料的协调小元素、线条或格纹结构",
    "texture_3": "从参考图提炼轻量点缀元素，小尺度 repeat",
    "forbidden_full_body_elements": ["不得进入满版纹理的完整主体/场景/文字/logo"]
  },
  "texture_micro_structure": {
    "texture_1": {
      "motif_scale_relative": "最小重复元素占 tile 宽度的 3-8%",
      "motif_count_per_tile": "每 tile 可见元素 12-20 个",
      "negative_space_ratio": "负空间占比 45-55%",
      "repeat_unit_description": "具体写出最小重复单元里有什么",
      "element_type_mix": {"botanical": 0.6, "geometric_dot": 0.3, "organic_line": 0.1}
    },
    "texture_2": {
      "motif_scale_relative": "协调元素占 tile 宽度的 2-6%",
      "motif_count_per_tile": "每 tile 可见元素 15-25 个",
      "negative_space_ratio": "负空间占比 50-60%",
      "repeat_unit_description": "具体写出协调 repeat 结构",
      "element_type_mix": {"botanical": 0.4, "geometric": 0.4, "organic_line": 0.2}
    },
    "texture_3": {
      "motif_scale_relative": "点缀元素占 tile 宽度的 1-4%",
      "motif_count_per_tile": "每 tile 可见元素 20-40 个",
      "negative_space_ratio": "负空间占比 60-75%",
      "repeat_unit_description": "具体写出极小规模点缀",
      "element_type_mix": {"botanical": 0.3, "geometric_dot": 0.5, "organic_line": 0.2}
    }
  },
  "hero_edge_contract": {
    "min_margin_ratio": 0.30,
    "edge_fade_pixels": "2-6px soft anti-aliased edge only",
    "forbidden_alpha_patterns": ["gradient halo", "semi-transparent halo around subject", "colored fringe on edge", "feathered edge wider than 8px"],
    "required_alpha_behavior": "keep the subject contour clean and readable on a pure white solid background without halo, fringe, or fake transparency artifacts"
  },
  "hero_texture_fusion_plan": "白底主图与三张纹理如何共享色彩、笔触、边缘处理和元素呼应",
  "source_images": [{"index": 1, "path": "/absolute/path/to/image.png", "role": "primary"}],
  "fusion_strategy": {"primary_reference": 1, "hero_subject_source": [1], "palette_sources": [1], "style_sources": [1], "strategy_note": ""},
  "theme_to_piece_strategy": {
    "base_atmosphere": "大身低噪底纹如何继承主题色彩/氛围，不直接复制主体",
    "hero_motif": "组合主卖点元素，建议放置在前片/指定 hero 裁片；如果 dominant_objects 中有多个 S/A 级 hero_motif，必须组合保留，不要三选一",
    "accent_details": "小花、叶片、蘑菇等只作小面积点缀",
    "quiet_zones": "袖片、后片、领口、窄条等需要安静处理的区域",
    "do_not_use_as_full_body_texture": ["不适合大面积满版的具象元素"]
  },
  "prompt_quality_check": {
    "texture_passed": false,
    "hero_passed": false,
    "rewrite_count": 0,
    "texture_violations": [],
    "hero_violations": []
  },
  "generated_prompts": {
    "hero_motif_1": "英文 white-background foreground hero motif prompt。结构要求：先写主体观察段（覆盖 identity/pose/expression/hair/clothing/props/accessories/composition/art_style_details 全部9维），再接白底定位图格式约束。必须：1) preserve and recreate the primary subject from reference image；2) complete uncropped subject, full head and hair visible；3) pure white solid background；4) clean crisp edges with no halo / no colored fringe；5) no shadow, no floor, no scenery, no garden, no foliage, no painted wash, no vignette；6) apparel placement graphic, commercial garment print",
    "texture_1": "一个最终英文正向 prompt，长度约70-120词，直接可用于图像生成。它表示面积最大的主底纹，必须只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。用途是商业上装大身面料印花，不是海报、贴纸、场景图、白底单主体图。必须与原图底纹在主题元素、排列方式、密度、色彩比例、线条粗细上高度一致。必须写成无缝平铺的 2D 面料印花，并与 texture_2、texture_3 共享同一色板与同一艺术风格。必须原样包含这些短语：seamless pattern, tileable, all-over print, flat 2D, no shading, no folds, fabric texture, commercial apparel textile。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。",
    "texture_2": "一个最终英文正向 prompt，长度约60-100词，直接可用于图像生成。它表示与 texture_1 协调的次级图案或辅助纹理，必须只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。它与 texture_1 使用完全相同的色彩体系和艺术表现语言，但在元素尺度、疏密、抽象程度上形成层次差异。必须是无缝平铺的 2D 面料图案，不能写成人物、服装效果、白底单主体。必须原样包含这些短语：seamless pattern, tileable, coordinated palette, flat 2D, no shading, fabric texture。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。",
    "texture_3": "一个最终英文正向 prompt，长度约40-80词，直接可用于图像生成。它表示最小尺度的微装饰纹理，只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。它必须与 texture_1、texture_2 保持同一色板和同一艺术风格，但重复单元最小、密度受控、只作为点缀。必须是无缝平铺的 2D 面料图案，不能出现白底主体、模特、穿着效果或场景。必须原样包含这些短语：micro pattern, small-scale repeat, seamless, tileable, flat 2D, accent detail, fabric texture, no shading。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。"
  }
}
```

## 任务

1. `dominant_objects`
   - 提取最突出的 1-3 个主体。
   - 每个主体必须写出：`name`、`grade(S|A|B|C)`、`description`、`suggested_usage`、`source_image_refs`、`geometry`、`garment_placement_hint`。

2. `supporting_elements`
   - 提取边框、背景、纹理、点缀等辅助元素，并标注 `source_image_refs`。

3. `palette`
   - 从图像真实提取 `primary/secondary/accent/dark` HEX，不要编造。

4. `style`
   - 输出 `medium`、`brush_quality`、`mood`、`pattern_density`、`line_style`、`overall_impression`。

5. `theme_to_piece_strategy`
   - 把主题工程化拆成 `base_atmosphere`、`hero_motif`、`accent_details`、`quiet_zones`、`do_not_use_as_full_body_texture`。
   - 如果 `dominant_objects` 中有多个 `grade in {S, A}` 且 `suggested_usage = hero_motif` 的主体，
     `theme_to_piece_strategy.hero_motif` 必须明确写出：组合保留全部主体，不要三选一。

6. `reference_fidelity` / `design_dna` / `single_texture_derivation` / `hero_texture_fusion_plan`
   - 明确主图必须保留什么、纹理从图中提炼什么，以及主图和纹理如何保持同一套设计语言。

7. `hero_edge_contract`
   - 如能判断请输出：
     - `min_margin_ratio`
     - `edge_fade_pixels`
     - `forbidden_alpha_patterns`
     - `required_alpha_behavior`
   - 默认要求：
     - `min_margin_ratio >= 0.30`
     - 仅允许 `2-6px` soft anti-aliased edge
     - 禁止 `gradient halo / semi-transparent halo / colored fringe`
     - 纯白实体背景上的主体边界要清晰，不得出现伪透明感

8. `generated_prompts`
   - 只生成英文 `hero_motif_1`、`texture_1`、`texture_2`、`texture_3` 四条提示词。
   - `texture_1/2/3` 保持当前 Web 项目用途：三条纯图案平铺纹理。
   - `hero_motif_1` 必须是前景主体白底图。

## hero_motif_1 特别要求

1. 先写主体观察段，再写白底格式约束。
2. 主体观察段必须覆盖 9 个维度：
- `subject_identity`
- `pose_action`
- `expression`
- `hair`
- `clothing`
- `props`
- `accessories`
- `composition`
- `art_style_details`

3. 如果某个维度观察不清晰，写 `not clearly visible`，不要编造。

4. 若存在多个 `S/A + hero_motif` 主体，`hero_motif_1` 必须保留全部主体，组合成一个 cohesive foreground placement graphic，不能三选一。

5. `hero_motif_1` 必须明确包含这些语义：
- `preserve and recreate the primary subject(s) from the user's reference image as much as possible`
- `isolated foreground motif only`
- `pure white background`
- `no shadow`
- `no floor`
- `no scenery`
- `clean crisp edges`
- `apparel placement graphic`
- `commercial garment print`
- `complete uncropped subject`
- `full head and hair visible`
- `centered complete subject`

6. `hero_motif_1` 禁止写成：
- `transparent PNG cutout`
- `real alpha background`
- `transparent background`
- `checkerboard transparency preview`
- `fake transparency grid`
- scene / garden / meadow / landscape / environment
- botanical backdrop / painted wash / vignette
- seamless / tileable / repeat pattern

## 主题元素分级规则

- S级：完整动物、人脸/人像、文字、商标、完整建筑、完整场景、复杂叙事插画。绝不能进入满版纹理，只能拒绝、简化或作为很小的定位 motif。
- A级：简化动物剪影、单朵大花、几何图标、单个清晰角色符号。只允许 hero 使用，不能满版。
- B级：小花、小叶、抽象笔触点缀、小型几何元素。只能作小面积 accent。
- C级：主题色彩晕染、无具象形状的抽象纹理、水彩底、低对比噪点底、低对比小循环几何。可作大身 base。

所有 S 级元素、以及不适合大身的 A 级元素，必须写入 `theme_to_piece_strategy.do_not_use_as_full_body_texture`。

## 重要约束

- 颜色必须从图像中真实提取，不要编造。
- prompt 必须是英文，可直接用于图像生成。
- `dominant_objects[]` 必须包含 `grade`。
- `dominant_objects[]` 必须包含 `garment_placement_hint`。
- `generated_prompts.texture_1/texture_2/texture_3` 必须是纯平铺纹理，不得出现白底主体、模特、穿着效果、场景。
- `generated_prompts.hero_motif_1` 必须出现 `pure white background`，且不得出现 `transparent png cutout`、`real alpha background`、`seamless`、`tileable`、`repeat pattern`。
- 人物、脸、角色、动物、商品、图标、物体都允许作为 `hero_motif_1` 的主体，只要它们是用户参考图的主要内容。

## 输出前自检

输出前逐条检查：
- `hero_motif_1` 是否覆盖了全部 9 个主体观察维度？
- 是否存在多个 hero 主体却只保留了一个？
- `theme_to_piece_strategy.hero_motif` 是否与多主体组合规则一致？
- `hero_motif_1` 是否仍然是白底图，而不是透明 cutout 或平铺纹理？
- `texture_1/2/3` 是否仍然保持纯图案平铺，没有 hero 词汇污染？
"""


def _merge_texture_prompt_b(raw: str, panel_id: str) -> str:
    text = raw or ""
    for pattern in _TEXTURE_CONTRADICTION_PATTERNS.get(panel_id, ()):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    base_contract = PANEL_DEFAULTS_EN.get(panel_id, "")
    if base_contract:
        text = f"{text}, {base_contract}" if text else base_contract
    return dedupe_prompt_chunks(clean_prompt_text(text))


def _collect_hero_subjects(visual_dict: dict) -> list[tuple[int, float, str, str]]:
    dominant = visual_dict.get("dominant_objects", [])
    candidates = []
    for obj in dominant:
        grade = str(obj.get("grade", "")).upper()
        usage = obj.get("suggested_usage", "")
        if grade in ("S", "A") and usage == "hero_motif":
            name = str(obj.get("name", "")).strip()
            desc = str(obj.get("description", "")).strip()
            form_type = str(obj.get("geometry", {}).get("form_type", "")).strip()
            ratio = obj.get("geometry", {}).get("canvas_ratio", 0) or 0
            label = f"{name}: {desc}" if name and desc else (name or desc)
            if form_type:
                label = f"{label} Form type: {form_type}."
            if label:
                candidates.append((2 if grade == "S" else 1, float(ratio), label, name or desc))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates


def _enrich_hero_prompt_b(visual: dict, base_hero_prompt: str) -> str:
    candidates = _collect_hero_subjects(visual)
    prefix_parts = []
    if candidates:
        prefix_parts.append("Subject visual facts from reference image: " + "; ".join(item[2] for item in candidates) + ".")
    if len(candidates) > 1:
        names = ", ".join(item[3] for item in candidates if item[3])
        prefix_parts.append(
            "Composite hero requirement: include every listed hero subject in one cohesive foreground apparel placement graphic. "
            "Preserve the recognizable relative roles from the reference image, keep each subject complete and readable, "
            "arrange them as a balanced compact group suitable for splitting across left and right front garment pieces, "
            "and simplify only minor background clutter. Do not omit any listed hero subject; do not reduce the hero graphic to only one subject."
            + (f" Required subjects: {names}." if names else "")
        )
    elif candidates:
        prefix_parts.append(
            "Preserve and recreate the listed hero subject from the reference image as much as possible, keeping the recognizable silhouette, "
            "color identity, pose, proportions, and key details."
        )
    if not prefix_parts:
        return base_hero_prompt
    return " ".join(prefix_parts) + " " + base_hero_prompt.strip()


def _prepare_visual_for_scheme_b(visual: dict) -> dict:
    prepared = dict(visual or {})
    prompts = dict(prepared.get("generated_prompts", {}) or {})
    theme_strategy = prepared.get("theme_to_piece_strategy", {})
    hero_subjects = _collect_hero_subjects(prepared)

    if isinstance(theme_strategy, dict) and len(hero_subjects) > 1:
        theme_strategy = dict(theme_strategy)
        subject_names = [item[3] for item in hero_subjects if item[3]]
        if subject_names:
            theme_strategy["hero_motif"] = (
                "组合主卖点定位图案：保留并组合 "
                + "、".join(subject_names)
                + "，形成一个可前片定位的白底主图，不做三选一。"
            )
        prepared["theme_to_piece_strategy"] = theme_strategy

    raw_hero = prompts.get("hero_motif_1", "")
    if raw_hero:
        prompts["hero_motif_1"] = _enrich_hero_prompt_b(prepared, raw_hero)
        prepared["generated_prompts"] = prompts

    return prepared


def _force_white_background_motif_prompt(prompt_text: str) -> str:
    required = (
        "isolated foreground motif only, pure white background, no shadow, no floor, no scenery, "
        "no background art, no extra objects, centered complete subject, full uncropped figure, "
        "clean crisp edges, apparel placement graphic, commercial garment print"
    )
    hero_required = (
        "hero_motif_1 must preserve and recreate the primary subject from the user's reference image as much as possible, "
        "people, faces, characters, animals, products, icons, objects, or logos are allowed if they are the user's main image content, "
        "keep the recognizable silhouette, color identity, pose, proportions, and key visual details, "
        "hero_motif_1 must be foreground subject only, no scene, no garden, "
        "no meadow, no landscape, no environment, no foliage behind subject, "
        "no botanical backdrop, no painted wash behind subject, no vignette, "
        "no transparent background, no alpha background, no PNG cutout, no ground shadow"
    )
    text = prompt_text.strip()
    replacements = {
        "transparent png cutout": "pure white background",
        "transparent background": "pure white background",
        "transparent alpha background": "pure white background",
        "alpha background": "pure white background",
        "real alpha background": "pure white background",
        "background removal": "pure white background",
        "checkerboard transparency preview": "pure white background",
        "fake transparency grid": "pure white background",
        "no background": "pure white background",
        "cutout": "clean crisp edges",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
        text = text.replace(old.title(), new)
        text = text.replace(old.upper(), new.upper())
    for old in (
        "plain light background",
        "plain warm background",
        "removable plain background",
        "removable plain backgrounds",
        "suitable for background removal",
        "botanical backdrop",
        "foliage behind subject",
        "painted wash behind subject",
        "garden background",
        "background art",
        "transparent",
        "alpha",
    ):
        text = text.replace(old, "pure white background")
    text = text.replace("as as possible", "as much as possible")
    lower = text.lower()
    if (
        "pure white background" in lower
        and "clean crisp edges" in lower
        and "apparel placement graphic" in lower
        and "commercial garment print" in lower
    ):
        return f"{text}, {hero_required}"
    return f"{text}, {required}, {hero_required}"


class HeroPromptStrategyB(HeroPromptStrategy):
    @property
    def vision_system_prompt(self) -> str:
        return VISION_SYSTEM_PROMPT_B

    def generate_texture_prompts(self, visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
        visual = _prepare_visual_for_scheme_b(visual)
        generated_prompts = visual.get("generated_prompts", {})
        texture_ids = ["hero_motif_1", "texture_1", "texture_2", "texture_3"]
        meta = {
            "hero_motif_1": ("AI生成主图白底图", "single_hero", "hero_motif_1", HERO_NEGATIVE_EN),
            "texture_1": ("纹理1", "single_texture", "base_texture", TEXTURE_NEGATIVE_EN),
            "texture_2": ("纹理2", "single_texture", "base_texture", TEXTURE_NEGATIVE_EN),
            "texture_3": ("纹理3", "single_texture", "base_texture", TEXTURE_NEGATIVE_EN),
        }

        prompts: list[dict] = []
        prompt_map: dict[str, str] = {}

        for tid in texture_ids:
            raw = generated_prompts.get(tid, "")
            if not raw:
                print(f"[WARN] LLM did not return prompt for {tid}, using empty string")

            if tid == "hero_motif_1":
                raw = _force_white_background_motif_prompt(raw)
                raw = dedupe_prompt_chunks(clean_prompt_text(raw))
            else:
                # Intentionally duplicated texture_1/2/3 behavior from scheme A so scheme B
                # remains self-contained and does not call back into scheme A at runtime.
                raw = _merge_texture_prompt_b(raw, tid)

            purpose, panel, role, negative = meta[tid]
            cleaned, cleaned_negative = prepare_image_generation_payload(raw, negative, strict=False)
            prompts.append(
                {
                    "texture_id": tid,
                    "purpose": purpose,
                    "prompt": cleaned,
                    "negative_prompt": cleaned_negative,
                    "panel": panel,
                    "role": role,
                }
            )
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
