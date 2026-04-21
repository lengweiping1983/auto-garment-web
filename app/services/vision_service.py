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
  },
  "generated_prompts": {
    "texture_1": "英文 seamless tileable visible repeat pattern prompt",
    "texture_2": "英文 coordinating seamless tileable visible repeat pattern prompt",
    "texture_3": "英文 small-scale accent repeat pattern prompt",
    "hero_motif_1": "英文 isolated foreground hero motif only as transparent PNG cutout prompt"
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
                "text": f"服装类型: {garment_type}\n季节: {season}\n用户附加提示: {user_prompt or '无'}\n\n请严格按照上方 schema 输出 JSON。",
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

        data = json.loads(content)
        # Inject source image path for downstream traceability
        data["source_images"] = [{"index": 1, "path": str(image_path.resolve()), "role": "primary"}]
        return data
