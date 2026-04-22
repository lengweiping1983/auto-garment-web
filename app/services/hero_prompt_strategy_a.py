"""Scheme A: current web-project hero prompt behavior."""

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


VISION_SYSTEM_PROMPT_A = """
# VLM 图像结构化提取系统提示词

## 角色与目标

你是**视觉解析专家**。将用户上传的图片转换为**极致详细的结构化文本描述**，目标是：另一位AI画师只读你的文字，能还原出与原图90%以上相似的图像。

以"盲人画师的语言翻译"自居——精确描述构成图像的每一个可量化要素，不抒情、不概括、不省略。

---

## 输出格式（强制）

必须严格按以下模板输出。无信息字段填 `"无"`，不可省略任何字段。
最终回复必须是**单个合法 JSON 对象**，不要输出 Markdown 说明、不要输出代码围栏、不要输出额外前后缀文字。
`generated_prompts` 中四个字段都必须是**可直接提交给图像模型的最终英文 prompt 字符串**，不是中文解释，不要写 "prompt:"、"here is"、"约100词"、"用于生成" 这类元话术。

```json
{
  "struct": {
    "subject": {
        "primary": {
        "category": "主体类别",
        "count": 1,
        "position": "画面中的精确位置和占比",
        "pose_action": "姿态、动作、朝向",
        "appearance": {
            "overall_shape": "整体轮廓",
            "color": {
            "dominant": "主色+近似HEX",
            "secondary": "辅色+近似HEX",
            "accent": "点缀色+近似HEX"
            },
            "texture_material": "材质与纹理",
            "surface_property": "表面光学特性（漫反射/镜面/半透明主体/柔和发光；若主体可透视，仅描述主体自身，不得推导为透明背景）",
            "fine_details": ["关键细节1", "关键细节2"]
        }
        },
        "secondary": [
        {
            "category": "次要主体",
            "relation_to_primary": "与主主体的空间关系",
            "description": "外观关键描述"
        }
        ]
    },

    "environment": {
        "scene_type": "室内/室外/纯色背景/抽象",
        "location_context": "具体场景",
        "layers": {
        "foreground": "前景",
        "midground": "中景",
        "background": "远景/背景",
        "ground_plane": "地面/基底"
        }
    },

    "lighting": {
        "primary_source": {
        "direction": "主光方向",
        "type": "光源类型",
        "color_temperature": "色温",
        "quality": "硬光/软光",
        "intensity": "相对强度"
        },
        "shadows": {
        "direction": "阴影方向",
        "hardness": "边缘硬度",
        "color": "阴影偏色"
        },
        "highlights": "高光区域"
    },

    "composition": {
        "perspective": "平视/俯视/仰视",
        "shot_type": "特写/近景/中景/全景",
        "camera_angle": "正面/侧面/3/4侧",
        "framing": "构图法则",
        "depth_of_field": "景深效果"
    },

    "color_palette": {
        "overall_temperature": "冷调/暖调/中性",
        "saturation": "高/中/低/去饱和",
        "contrast": "高/中/低",
        "dominant_colors": [
        {"name": "颜色名", "hex": "#000000", "area_ratio": "占比"}
        ]
    },

    "style": {
        "artistic_style": "写实/插画/3D/油画/其他",
        "rendering_technique": "照片/数字绘画/CGI/矢量",
        "mood_emotion": "情绪氛围"
    },

    "text_symbols": {
        "has_text": false,
        "text_elements": [
        {
            "content": "文字内容",
            "location": "位置",
            "font_style": "字体风格",
            "color": "颜色"
        }
        ],
        "logos_brands": "品牌标识",
        "symbols_patterns": "图案符号"
    },

    "micro_details": {
        "easily_missed": [
        "最容易被忽略但影响还原的细节1",
        "细节2",
        "细节3"
        ],
        "imperfections": "刻意的不完美：褶皱、毛孔、划痕等"
    }
  },
  "generated_prompts": {
    "hero_motif_1": "一个最终英文正向 prompt，长度约100-220词，直接可用于图像生成。基于 struct 中主主体与次主体信息，只描述最终要生成的定位印花主体，不要解释过程，不要写中文，不要写提示语说明。用途是商业上装的白底定位印花（placement print），不是海报、贴纸、包装图或整件服装效果图。必须写入：主体精确类别与数量、整体轮廓与体量、主色/辅色/点缀色及近似 HEX、主体自身材质与表面光学特性、姿态动作朝向、关键纹样与边缘特征。若主体本身可透光或半透明，只能描述主体自身质感，绝不能把背景写成透明。必须原样包含这些短语：isolated foreground subject only, pure white background, no shadow, no floor, no scenery, no extra objects, no text, no logo, no watermark, centered complete subject, full uncropped figure, clean crisp edges, apparel placement graphic, apparel-safe print graphic。禁止出现：transparent background, alpha background, PNG cutout, background removal, checkerboard preview, fake transparency grid, sticker cutout, isolated on transparent, seamless, tileable, repeat pattern, all-over print, fabric swatch, wallpaper, packaging paper, garment mockup, fashion model, mannequin, person wearing garment, 3D render。",
    "texture_1": "一个最终英文正向 prompt，长度约70-120词，直接可用于图像生成。它表示面积最大的主底纹，必须只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。用途是商业上装大身面料印花，不是海报、贴纸、场景图、白底单主体图。必须与原图底纹在主题元素、排列方式、密度、色彩比例、线条粗细上高度一致。必须写成无缝平铺的 2D 面料印花，并与 texture_2、texture_3 共享同一色板与同一艺术风格。必须原样包含这些短语：seamless pattern, tileable, all-over print, flat 2D, flat color, no folds, fabric texture, apparel-safe textile design。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。",
    "texture_2": "一个最终英文正向 prompt，长度约60-100词，直接可用于图像生成。它表示与 texture_1 协调的次级图案或辅助纹理，必须只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。它与 texture_1 使用完全相同的色彩体系和艺术表现语言，但在元素尺度、疏密、抽象程度上形成层次差异。必须是无缝平铺的 2D 面料图案，不能写成人物、服装效果、白底单主体。必须原样包含这些短语：seamless pattern, tileable, coordinated palette, flat 2D, flat color, fabric texture。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。",
    "texture_3": "一个最终英文正向 prompt，长度约40-80词，直接可用于图像生成。它表示最小尺度的微装饰纹理，只描述纯图案本身，不要解释过程，不要写中文，不要写任何元说明。它必须与 texture_1、texture_2 保持同一色板和同一艺术风格，但重复单元最小、密度受控、只作为点缀。必须是无缝平铺的 2D 面料图案，不能出现白底主体、模特、穿着效果或场景。必须原样包含这些短语：micro pattern, small repeat, seamless, tileable, flat 2D, delicate detail, fabric texture, flat color。禁止出现：pure white background, isolated foreground subject only, centered complete subject, full uncropped figure, placement graphic, transparent background, alpha background, garment mockup, fashion model, mannequin, person wearing garment, scenery, poster, sticker, product photo。"
  }
}
```

---

## 描述原则

1. **精确优于诗意**
   - ❌ "漂亮的蓝色"
   - ✅ "深靛蓝 (#1a237e)，仅在受光面可见"

2. **空间关系量化**
   - ❌ "在左边"
   - ✅ "位于画面左侧1/3区域，高度占画面60%，底部距下边缘10%"

3. **质感必须可翻译**
   - 描述表面如何与光互动，而非仅命名材质
   - ✅ "哑光麂皮，无镜面高光，边缘有0.5mm深色包边"

4. **不遗漏任何文字**
   - 图中所有文字精确转录，包括字体风格、颜色、描边、相对大小

5. **光影必须可重建**
   - 明确光源方向、色温、软硬，让画师能据此布光

6. **纹理必须可平铺且适合成衣（关键）**
   - texture_1/2/3 的提示词**只描述纯图案本身**，严禁出现服装版型、褶皱、人体、模特、光影、场景、3D 效果。它们是"面料印花图案"，不是"穿着效果图"。
   - ✅ 正确示例: "seamless tropical leaf pattern, dense overlapping monstera and palm fronds in emerald and sage green on off-white ground, flat 2D vector style, tileable, all-over print, flat color, fabric texture"
   - ❌ 错误示例: "a dress with floral pattern, soft lighting, beautiful model, draped fabric with folds"
   - 三个纹理之间必须保持**色彩共享**（使用相同的色板）和**风格统一**（相同的艺术表现手法），仅在图案密度、元素尺度、复杂度上拉开层次。
   - texture_1 对应图片中**面积最大**的底纹；texture_2 对应**次要**图案或抽象变体；texture_3 对应**最小尺度**的装饰性微图案。

7. **主图白底要求不得歧义（关键）**
   - hero_motif_1 必须输出为**纯白实体背景**的定位印花主体，不是透明底、不是可抠图预览、不是贴纸 cutout。
   - 如果主体本身具有玻璃、水晶、薄纱、果冻、冰块等透光或半透明特征，只能描述**主体自身**的透光质感，绝不允许把背景写成 transparent / alpha / cutout / background removal / checkerboard。
   - ✅ 正确示例: "glass bird motif with translucent wings, isolated foreground subject only, pure white background, clean crisp edges"
   - ❌ 错误示例: "transparent background png cutout of a glass bird"

8. **禁止输出自相矛盾的 prompt（关键）**
   - hero_motif_1 绝不能同时出现白底单主体要求与平铺纹理要求。例如不能同时写 `pure white background` 和 `seamless pattern`。
   - texture_1/2/3 绝不能同时出现平铺纹理要求与白底单主体要求。例如不能同时写 `tileable` 和 `centered complete subject`。
   - 若原图信息与商业成衣生成目标冲突，优先服从商业成衣目标：主图输出白底定位主体，纹理输出可平铺纯图案。
   - 输出前先检查一遍：每个 prompt 内不允许同时出现互相冲突的背景、构图、用途词。

9. **主动规避敏感词、违禁词与高风险表达（关键）**
   - 你生成的 `generated_prompts` 会直接进入生图链路，因此必须主动规避可能触发内容安全审核、供应商 moderation、敏感词过滤、违禁词过滤的表达。
   - 禁止输出任何涉及：色情/裸露、暴力/血腥、武器、毒品、自残、仇恨、极端主义、虐待、未成年人不当内容、违法行为、NSFW、露骨身体描述。
   - 即使用户原图或主题中含有高风险联想，也必须改写成**安全、商业、服装可生产**的视觉语言，不能把敏感词原样写进 prompt。
   - 优先使用安全替代表达，而不是危险原词。例如：
     - `nude` -> `skin-tone beige`
     - `blood` -> `deep crimson`
     - `knife/blade` -> `sharp geometric motif` / `leaf-shaped motif`
     - `sexy/sensual/provocative` -> `elegant commercial` / `soft elegant` / `bold commercial`
   - 若某些主体或细节天然高风险，不要直写危险物；改写为抽象图形、颜色、材质、轮廓、 botanical / geometric motif、apparel-safe prop。
   - negative prompt 也不能堆砌敏感词清单；应尽量使用安全的商业约束词，例如 `apparel-safe`, `no policy-risk content`, `family-friendly design language`, `apparel-safe design language`。
   - 如果无法在不使用敏感词的情况下准确描述，就优先保留安全的形状、配色、材质、轮廓和构图信息，宁可更抽象，也不要输出危险原词。

---

## 自检（输出前默念）

遮住原图，仅凭我的描述：
- 画师知道每个物体的**精确位置**吗？
- 我给出了**可量化的比例**吗？
- **光影方向**足够明确吗？
- **色彩**有近似HEX值吗？
- 图中**所有文字**都转录了吗？
- 我补充了**最容易被忽略的3个关键细节**吗？
- hero_motif_1 是否仍然保持纯白实体背景，没有任何 transparent / cutout / tileable / repeat 冲突词？
- texture_1/2/3 是否仍然保持纯图案平铺，没有任何 white background / centered subject / mannequin / wearing garment 冲突词？
- 我是否已经主动规避了敏感词、违禁词和容易触发审核的高风险表达？
"""


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
        r"\b(?:handwritten|printed|decorative)\s+text\b",
        r"\b(?:words?|letters?|typography|caption|title|label)s?\b",
        r"\b(?:logo|watermark|signage)\b",
        r"\bsoft focus\b",
        r"\bout-?of-?focus\b",
        r"\bbokeh\b",
        r"\bdepth of field\b",
        r"\bshallow depth of field\b",
        r"\bmisty\b",
        r"\bhazy\b",
        r"\bfoggy\b",
        r"\bdreamy\b",
        r"\bethereal\b",
        r"\bfuzzy\b",
        r"\bwashed out\b",
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
        r"\b(?:handwritten|printed|decorative)\s+text\b",
        r"\b(?:words?|letters?|typography|caption|title|label)s?\b",
        r"\b(?:logo|watermark|signage)\b",
        r"\bsoft focus\b",
        r"\bout-?of-?focus\b",
        r"\bbokeh\b",
        r"\bdepth of field\b",
        r"\bshallow depth of field\b",
        r"\bmisty\b",
        r"\bhazy\b",
        r"\bfoggy\b",
        r"\bdreamy\b",
        r"\bethereal\b",
        r"\bfuzzy\b",
        r"\bwashed out\b",
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
        r"\b(?:handwritten|printed|decorative)\s+text\b",
        r"\b(?:words?|letters?|typography|caption|title|label)s?\b",
        r"\b(?:logo|watermark|signage)\b",
        r"\bsoft focus\b",
        r"\bout-?of-?focus\b",
        r"\bbokeh\b",
        r"\bdepth of field\b",
        r"\bshallow depth of field\b",
        r"\bmisty\b",
        r"\bhazy\b",
        r"\bfoggy\b",
        r"\bdreamy\b",
        r"\bethereal\b",
        r"\bfuzzy\b",
        r"\bwashed out\b",
    ),
}


def _ensure_white_background_hero(prompt: str) -> str:
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


def _merge_panel_prompt(raw: str, panel_id: str) -> str:
    text = raw or ""
    for pattern in _PANEL_CONTRADICTION_PATTERNS.get(panel_id, ()):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    base_contract = PANEL_DEFAULTS_EN.get(panel_id, "")
    if base_contract:
        text = f"{text}, {base_contract}" if text else base_contract
    return dedupe_prompt_chunks(clean_prompt_text(text))


class HeroPromptStrategyA(HeroPromptStrategy):
    @property
    def vision_system_prompt(self) -> str:
        return VISION_SYSTEM_PROMPT_A

    def generate_texture_prompts(self, visual: dict, out_dir: Path) -> tuple[dict[str, str], dict]:
        generated_prompts = visual.get("generated_prompts", {})
        texture_ids = ["hero_motif_1", "texture_1", "texture_2", "texture_3"]
        meta = {
            "hero_motif_1": ("AI生成主图白底定位图案", "single_hero", "hero_motif_1", HERO_NEGATIVE_EN),
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
                raw = _ensure_white_background_hero(raw)
            raw = _merge_panel_prompt(raw, tid)
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
