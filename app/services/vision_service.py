"""Vision analysis service — constructs AI vision prompt and parses visual_elements.

This module replaces the CLI script `视觉元素提取.py`.
The LLM prompt is FIXED (no thinking required from LLM), but the output schema
preserves ALL fields needed by downstream pipeline stages.
"""
import base64
import json
from pathlib import Path

from app.config import settings
from app.core.llm_client import LLMClient


def _fix_truncated_json(text: str) -> str:
    """Attempt to repair JSON truncated by token limit.

    Counts unclosed braces/brackets/quotes and appends closing tokens.
    """
    stack = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                stack.append('"')
            elif stack and stack[-1] == '"':
                stack.pop()
                in_string = False
            i += 1
            continue
        if in_string:
            i += 1
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
        i += 1

    # Append missing closers in reverse order
    suffix = ""
    for opener in reversed(stack):
        if opener == '"':
            suffix += '"'
        elif opener == "{":
            suffix += "}"
        elif opener == "[":
            suffix += "]"

    # Heuristic: if the truncated part is in the middle of a string value,
    # we may need to close the string, then the containing object/array.
    # The stack-based approach above handles structural closers;
    # for a dangling string we already appended '"'.
    return text + suffix


VISION_SYSTEM_PROMPT = """
# VLM 图像结构化提取系统提示词

## 角色与目标

你是**视觉解析专家**。将用户上传的图片转换为**极致详细的结构化文本描述**，目标是：另一位AI画师只读你的文字，能还原出与原图90%以上相似的图像。

以"盲人画师的语言翻译"自居——精确描述构成图像的每一个可量化要素，不抒情、不概括、不省略。

---

## 输出格式（强制）

必须严格按以下模板输出。无信息字段填 `"无"`，不可省略任何字段。

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
            "surface_property": "表面光学特性（漫反射/镜面/透明/发光）",
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
    "hero_motif_1": "英文白底服装定位印花图案生成提示词，约100-300词。基于上方 struct 结构化数据中 subject.primary（主主体）和 subject.secondary（次要主体）的完整描述，提炼并扩展成一个可直接提交给 AI 图像模型的最终英文 prompt，无需任何后处理。此图案用于商业成衣（T恤、衬衫、防晒服等上装）的定位印花（placement print），印在前胸、后背或侧缝等服装部位，不是装饰画、海报或贴纸。必须逐条包含：1) 主体精确类别与数量；2) 整体轮廓与体量感；3) 主色/辅色/点缀色（附近似 HEX 值）；4) 材质纹理与表面光学特性（哑光/镜面/透明/发光）；5) 姿态、动作、朝向；6) 所有关键细节（花纹、配饰、表情、肌理、边缘特征）；7) 纯白硬底拍摄式背景与清晰边缘要求。强制关键词（必须原样包含）：isolated foreground subject only, pure white background, no shadow, no floor, no scenery, no extra objects, no text, no logo, no watermark, centered complete subject, full uncropped figure, clean crisp edges, apparel placement graphic, commercial garment print。严禁：服装版型、褶皱、人体穿着效果、模特、光影场景、背景画面、画框/贴纸排版、渐变色背景、彩色背景盒、3D 渲染效果。",
    "texture_1": "英文无缝平铺服装面料印花生成提示词，约80-120词。基于对原图最主要、最大面积底纹/图案的精确观察，生成一个可直接提交给 AI 图像模型的最终英文 prompt，无需任何后处理。此纹理用于商业成衣（T恤、衬衫、防晒服等上装）的大身面料印花，覆盖前身、后身等主要裁片，不是壁纸、包装纸或装饰画。必须与图片底纹 100% 吻合（图案类型、主题元素、排列方式、疏密程度、色彩比例、线条粗细）。必须是全屏无缝平铺纹理（seamless tileable all-over fabric print），无边界感，无中心焦点，无透视变形，flat 2D 纯图案，无阴影，无褶皱，无服装形态。强制包含：seamless pattern, tileable, all-over print, flat 2D, no shading, no folds, fabric texture, commercial apparel textile。此纹理与 texture_2、texture_3 共享同一色板（主色/辅色/点缀色一致）和艺术风格（画笔质感、线条语言、饱和度范围）。",
    "texture_2": "英文协调无缝平铺服装面料印花生成提示词，约60-100词。基于对原图次要图案或辅助纹理的精确观察，生成一个可直接提交给 AI 图像模型的最终英文 prompt，无需任何后处理。此纹理用于商业成衣（T恤、衬衫、防晒服等上装）的拼接部位面料印花，如袖子、侧缝、领贴、内衬等裁片，不是壁纸或装饰画。与 texture_1 共享完全相同的色彩体系（主色/辅色/点缀色）和艺术风格（画笔质感、线条粗细、饱和度范围），但在图案密度或元素尺度上形成层次差异（可更稀疏、更抽象、更几何化或更细碎）。同样必须是无缝平铺（seamless tileable），flat 2D 纯图案，无阴影，无服装形态。强制包含：seamless pattern, tileable, coordinated palette, flat 2D, no shading, fabric texture。",
    "texture_3": "英文微观装饰服装面料印花生成提示词，约40-80词。基于对原图最小尺度装饰性纹理的精确观察，生成一个可直接提交给 AI 图像模型的最终英文 prompt，无需任何后处理。此纹理用于商业成衣（T恤、衬衫、防晒服等上装）的小面积点缀面料印花，如领口罗纹、袖口边、下摆边、口袋贴布等细节裁片，不是壁纸或装饰画。与 texture_1/texture_2 保持同一色板和同一艺术风格，但尺度最小（重复单元约 2-5cm），密度受控，仅作为点缀使用。必须是无缝平铺纯图案（seamless tileable flat 2D），无任何服装结构暗示。强制包含：micro pattern, small-scale repeat, seamless, tileable, flat 2D, accent detail, fabric texture, no shading。"
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
   - ✅ 正确示例: "seamless tropical leaf pattern, dense overlapping monstera and palm fronds in emerald and sage green on off-white ground, flat 2D vector style, tileable, all-over print, no shading, fabric texture"
   - ❌ 错误示例: "a dress with floral pattern, soft lighting, beautiful model, draped fabric with folds"
   - 三个纹理之间必须保持**色彩共享**（使用相同的色板）和**风格统一**（相同的艺术表现手法），仅在图案密度、元素尺度、复杂度上拉开层次。
   - texture_1 对应图片中**面积最大**的底纹；texture_2 对应**次要**图案或抽象变体；texture_3 对应**最小尺度**的装饰性微图案。

---

## 自检（输出前默念）

遮住原图，仅凭我的描述：
- 画师知道每个物体的**精确位置**吗？
- 我给出了**可量化的比例**吗？
- **光影方向**足够明确吗？
- **色彩**有近似HEX值吗？
- 图中**所有文字**都转录了吗？
- 我补充了**最容易被忽略的3个关键细节**吗？

"""


class VisionService:
    def __init__(self):
        self.client = LLMClient()

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def analyze_theme_image(
        self,
        image_path: Path,
        garment_type: str = "commercial apparel sample",
        season: str = "spring/summer",
        user_prompt: str = "",
    ) -> dict:
        """Run fixed vision analysis prompt against the theme image.

        Returns the FULL visual_elements dict (same schema as CLI version)
        so downstream stages don't lose any fields.
        """
        b64_image = self._encode_image(image_path)
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

        user_content = [
            {
                "type": "text",
                "text": f"服装类型: {garment_type}\n季节: {season}\n用户需求: {user_prompt or '无'}\n\n请严格按照上方 schema 输出 JSON。所有生成的纹理和图案必须适合用于商业服装成衣生产（T恤、衬衫、防晒服等上装的面料印花和定位印花），不是装饰画、壁纸或包装纸。",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_image}"},
            },
        ]

        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        content = await self.client.chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=16384,
        )

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("\n", 1)[0]
        if content.startswith("json"):
            content = content.split("\n", 1)[1]

        content = content.strip()
        # Fix truncated JSON by closing unclosed braces/brackets
        content = _fix_truncated_json(content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            # Log raw response for debugging; save to work dir if possible
            print(f"[ERROR] Vision LLM returned invalid JSON: {exc}")
            print(f"[ERROR] Raw content (first 2000 chars): {content[:2000]}")
            raise RuntimeError(
                f"视觉分析返回的 JSON 解析失败。请检查 LLM 输出格式。原始错误: {exc}"
            ) from exc

        # Inject source image path for downstream traceability
        data["source_images"] = [{"index": 1, "path": str(image_path.resolve()), "role": "primary"}]
        return data
