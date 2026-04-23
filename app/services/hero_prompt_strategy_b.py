"""Scheme B: structured white-background hero prompt while keeping A textures."""

from __future__ import annotations

from pathlib import Path
import re

from app.core.prompt_blocks import PANEL_DEFAULTS_EN

from app.services.hero_prompt_strategy_base import (
    HeroPromptStrategy,
    clean_prompt_text,
    dedupe_prompt_chunks,
    normalize_image_generation_prompt,
)


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

4. 所有 prompt 都必须是**英文 正向 prompt 字符串**，不是中文说明，不要写 `prompt:`、`here is`、`for generation` 之类元话术。

## 输出 JSON schema（至少遵守以下结构）

```json
{
  "dominant_objects": [
    {
      "name": "主体名",
      "type": "main_subject",
      "grade": "S|A|B|C",
      "description": "",
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
        "recommended_width_ratio_in_piece": 0,
        "recommended_height_ratio_in_piece": 0,
        "recommended_anchor": "chest_center|center|small_accent|do_not_place",
        "anti_examples": [""]
      }
    }
  ],
  "supporting_elements": [
    {"name": "元素名", "type": "decoration|background|texture|frame", "description": "...", "source_image_refs": [1]}
  ],
  "palette": {"primary": ["#hex"], "secondary": ["#hex"], "accent": ["#hex"], "dark": ["#hex"]},
  "style": {"medium": "", "brush_quality": "", "mood": "", "pattern_density": "low|medium|high", "line_style": "", "overall_impression": ""},
  "reference_fidelity": {
    "must_preserve": [""],
    "may_simplify": [""],
    "must_not_change": [""]
  },
  "design_dna": {
    "shared_palette": ["#hex"],
    "motif_vocabulary": [""],
    "linework": "",
    "brushwork": "",
    "material_feel": "",
    "negative_space": "",
    "fusion_rule": ""
  },
  "hero_edge_contract": {
    "min_margin_ratio": 0,
    "edge_fade_pixels": "",
    "forbidden_alpha_patterns": ["gradient halo", "semi-transparent halo around subject", "colored fringe on edge", "feathered edge wider than 8px"],
    "required_alpha_behavior": "keep the subject contour clean and readable on a pure white solid background without halo, fringe, or artificial transparency artifacts"
  },
  "hero_texture_fusion_plan": "",
  "source_images": [{"index": 1, "path": "/absolute/path/to/image.png", "role": "primary"}],
  "fusion_strategy": {"primary_reference": 1, "hero_subject_source": [1], "palette_sources": [1], "style_sources": [1], "strategy_note": ""},
  "theme_to_piece_strategy": {
    "base_atmosphere": "",
    "hero_motif": "如果 dominant_objects 中有多个 S/A 级 hero_motif，必须组合保留，不要三选一，并让主体之间保持可见间距，不要贴在一起",
    "accent_details": "",
    "quiet_zones": "",
    "do_not_use_as_full_body_texture": [""]
  },
  "prompt_quality_check": {
    "texture_passed": false,
    "hero_passed": false,
    "rewrite_count": 0,
    "texture_violations": [],
    "hero_violations": []
  },
  "generated_prompts": {
    "texture_micro_structure": {
      "texture_1": {
        "motif_scale_guidance": "具体写出 纹理图案方案 A 重复元素组织方式",
        "density_guidance": "",
        "negative_space_guidance": "",
        "repeat_unit_description": "具体写出 纹理图案方案 A 重复组织方式如何建立协调的 repeat 节奏",
        "element_bias": ""
      },
      "texture_2": {
        "motif_scale_guidance": "具体写出 纹理图案方案 B 重复元素组织方式",
        "density_guidance": "",
        "negative_space_guidance": "",
        "repeat_unit_description": "具体写出 纹理图案方案 B 重复组织方式如何建立协调的 repeat 节奏",
        "element_bias": ""
      },
      "texture_3": {
        "motif_scale_guidance": "具体写出 纹理图案方案 C 重复元素组织方式",
        "density_guidance": "",
        "negative_space_guidance": "",
        "repeat_unit_description": "具体写出 纹理图案方案 C 重复组织方式如何建立协调的 repeat 节奏",
        "element_bias": ""
      }
    },
    "hero_motif_1": "英文 white-background foreground hero motif prompt。结构要求：先写主体观察段（覆盖 identity/pose/expression/hair/clothing/props/accessories/composition/art_style_details 全部9维），再接白底定位图格式约束。必须：1) preserve and recreate the primary subject from reference image；2) complete uncropped subject, full head and hair visible；3) pure white solid background；4) clean crisp edges with no halo / no colored fringe；5) no shadow, no floor, no scenery, no garden, no foliage, no painted wash, no vignette；6) apparel placement graphic, apparel-safe print graphic",
    "texture_1": "按照用户的需求与参考图中的整体风格、背景气质、色彩关系和图中的纹理线索，你需要大胆创新，并设计或复刻一套适合衣服使用的平铺纹理图案方案 A。它不能包含主体、大图案、场景或文字，必须由小尺度 repeat 元素组成。texture_1 应从参考图中提炼第一套清晰独立的视觉家族或组织方式，形成自然、松散、较通透的重复节奏；它需要与 texture_2、texture_3 明显不同，差异应来自图案组织方式、元素关系、节奏结构或视觉家族，而不是只靠尺寸、疏密或同一语言的轻微变化。输出一个最终英文正向 prompt，直接可用于图像生成。它必须是一句或数句流畅自然的成品 prompt，不是规格说明、不是分析、不是 checklist、不是参数表；不要输出字段名、标签、百分比、范围、配比、JSON 风格结构，也不要复述本任务要求。只描述最终可见的纯图案本身，不要解释过程，不要写中文，不要写任何元说明。必须写成英文 seamless tileable visible repeat pattern prompt，必须由适合衣服使用的小尺度 repeat 元素组成。texture_1 必须与 texture_2、texture_3 明显不同，但差异主要来自当前图片中的另一类视觉组织方式，而不是只靠尺寸与疏密变化；它应呈现小型重复元素、稳定节奏、较通透的负空间，但这些约束只能通过自然英文描述隐含表达，不能写成数字条目。禁止写成 abstract wash、plain texture、paper grain only、gradient、empty background、tonal atmosphere only、blurred background、scene、landscape。",
    "texture_2": "按照用户的需求与参考图中的整体风格、背景气质、色彩关系和图中的纹理线索，你需要大胆创新，并设计或复刻一套适合衣服使用的平铺纹理图案方案 B。它不能包含主体、大图案、场景或文字，必须由小尺度 repeat 元素组成。texture_2 应从参考图中提炼第二套清晰独立的视觉家族或组织方式，形成自然、松散、较通透的重复节奏；它需要与 texture_1、texture_3 明显不同，差异应来自图案组织方式、元素关系、节奏结构或视觉家族，而不是只靠尺寸、疏密或同一语言的轻微变化。输出一个最终英文正向 prompt，直接可用于图像生成。它必须是一句或数句流畅自然的成品 prompt，不是规格说明、不是分析、不是 checklist、不是参数表；不要输出字段名、标签、百分比、范围、配比、JSON 风格结构，也不要复述本任务要求。只描述最终可见的纯图案本身，不要解释过程，不要写中文，不要写任何元说明。必须写成英文 seamless tileable visible repeat pattern prompt，必须由适合衣服使用的小尺度 repeat 元素组成。texture_2 必须与 texture_1、texture_3 明显不同，但差异主要来自当前图片中的另一类视觉组织方式，而不是只靠尺寸与疏密变化；它应呈现小型重复元素、稳定节奏、较通透的负空间，但这些约束只能通过自然英文描述隐含表达，不能写成数字条目。禁止写成 abstract wash、plain texture、paper grain only、gradient、empty background、tonal atmosphere only、blurred background、scene、landscape。",
    "texture_3": "按照用户的需求与参考图中的整体风格、背景气质、色彩关系和图中的纹理线索，你需要大胆创新，并设计或复刻一套适合衣服使用的平铺纹理图案方案 C。它不能包含主体、大图案、场景或文字，必须由小尺度 repeat 元素组成。texture_3 应从参考图中提炼第三套清晰独立的视觉家族或组织方式，形成自然、松散、较通透的重复节奏；它需要与 texture_1、texture_2 明显不同，差异应来自图案组织方式、元素关系、节奏结构或视觉家族，而不是只靠尺寸、疏密或同一语言的轻微变化。输出一个最终英文正向 prompt，直接可用于图像生成。它必须是一句或数句流畅自然的成品 prompt，不是规格说明、不是分析、不是 checklist、不是参数表；不要输出字段名、标签、百分比、范围、配比、JSON 风格结构，也不要复述本任务要求。只描述最终可见的纯图案本身，不要解释过程，不要写中文，不要写任何元说明。必须写成英文 seamless tileable visible repeat pattern prompt，必须由适合衣服使用的小尺度 repeat 元素组成。texture_3 必须与 texture_1、texture_2 明显不同，但差异主要来自当前图片中的另一类视觉组织方式，而不是只靠尺寸与疏密变化；它应呈现小型重复元素、稳定节奏、较通透的负空间，但这些约束只能通过自然英文描述隐含表达，不能写成数字条目。禁止写成 abstract wash、plain texture、paper grain only、gradient、empty background、tonal atmosphere only、blurred background、scene、landscape。"
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
     `theme_to_piece_strategy.hero_motif` 必须明确写出：组合保留全部主体，不要三选一；主体之间保留可见留白和呼吸感，不要贴合、重叠或共边。

6. `reference_fidelity` / `design_dna` / `hero_texture_fusion_plan`
   - 明确主图必须保留什么。

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
   - `texture_1/2/3` 三条纯图案平铺纹理。
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

4. 若存在多个 `S/A + hero_motif` 主体，`hero_motif_1` 必须保留全部主体，组合成一个 cohesive foreground placement graphic，不能三选一；但主体不能挤成一团，必须彼此分开并保留可见间距。

5. `hero_motif_1` 必须明确包含这些语义：
- `preserve and recreate the primary subject(s) from the user's reference image as much as possible`
- `isolated foreground motif only`
- `pure white background`
- `no shadow`
- `no floor`
- `no scenery`
- `clean crisp edges`
- `apparel placement graphic`
- `apparel-safe print graphic`
- `complete uncropped subject`
- `full head and hair visible`
- `centered complete subject`

7. 多主体排布要求（关键）
- 当 `hero_motif_1` 中存在多个主体时，必须把它们排成一个 balanced separated group，而不是 compact cluster。
- 主体之间必须保留 moderate spacing / visible white gap / breathing room。
- 禁止主体之间 touching / overlap / merged silhouette / shared outer contour / heavy occlusion。
- 每个主体都必须 individually readable、individually extractable、轮廓独立完整。
- 若主体数量较多，可适度缩小单个主体来换取间距，但不能删除主体，也不能把多个主体压成一个连在一起的大轮廓。

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
- 你生成的所有 prompt 都会直接进入生图链路，因此必须主动规避可能触发内容安全审核、敏感词过滤、违禁词过滤、供应商 moderation 的表达。
- 禁止输出任何涉及：色情/裸露、暴力/血腥、武器、毒品、自残、仇恨、极端主义、虐待、未成年人不当内容、违法行为、NSFW、露骨身体描述。
- 即使参考图主题中存在高风险联想，也必须改写成**安全、商业、服装可生产**的视觉语言，不能把敏感词原样写进 prompt。
- 优先使用安全替代表达，而不是危险原词。例如：
  - `nude` -> `skin-tone beige`
  - `blood` -> `deep crimson`
  - `knife/blade` -> `sharp geometric motif` / `leaf-shaped motif`
  - `sexy/sensual/provocative` -> `elegant commercial` / `soft elegant` / `bold commercial`
- 若某些主体或细节天然高风险，不要直写危险物；改写为抽象图形、配色、材质、轮廓、 botanical / geometric motif、apparel-safe prop。

## 输出前自检

输出前逐条检查：
- `hero_motif_1` 是否覆盖了全部 9 个主体观察维度？
- 是否存在多个 hero 主体却只保留了一个？
- `theme_to_piece_strategy.hero_motif` 是否与多主体组合规则一致？
- `hero_motif_1` 是否仍然是白底图，而不是透明 cutout 或平铺纹理？
- `texture_1/2/3` 是否仍然保持纯图案平铺，没有 hero 词汇污染？
- 我是否已经主动规避了敏感词、违禁词和容易触发审核的高风险表达？
"""


def _merge_texture_prompt_b(raw: str, panel_id: str) -> str:
    text = raw or ""
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
            "arrange them as a balanced separated group suitable for splitting across left and right front garment pieces, "
            "keep moderate spacing and visible white breathing room between subjects, and do not let subjects touch, overlap, merge, or share outer contours. "
            "Keep every subject individually readable and individually extractable, and if needed scale subjects slightly smaller to preserve separation while keeping all of them. "
            "Simplify only minor background clutter. Do not omit any listed hero subject; do not reduce the hero graphic to only one subject; do not collapse the group into a compact cluster."
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
                "保留并组合 "
                + "、".join(subject_names)
                + "，形成一个可前片定位的白底主图，不做三选一；主体之间保持清晰可见的间距和呼吸感，不要贴合、重叠或连成一个外轮廓。"
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
        "clean crisp edges, apparel placement graphic, apparel-safe print graphic"
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
        and "apparel-safe print graphic" in lower
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
            "hero_motif_1": ("AI生成主图白底图", "single_hero", "hero_motif_1"),
            "texture_1": ("纹理1", "single_texture", "base_texture"),
            "texture_2": ("纹理2", "single_texture", "base_texture"),
            "texture_3": ("纹理3", "single_texture", "base_texture"),
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

            purpose, panel, role = meta[tid]
            cleaned = normalize_image_generation_prompt(raw, strict=False)
            prompts.append(
                {
                    "texture_id": tid,
                    "purpose": purpose,
                    "prompt": cleaned,
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
            item["prompt"] = normalize_image_generation_prompt(
                item.get("prompt", ""),
                strict=False,
            )

        prompt_map = {p["texture_id"]: p["prompt"] for p in texture_prompts["prompts"]}
        return prompt_map, texture_prompts
