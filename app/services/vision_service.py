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
from app.services.hero_prompt_strategy_selector import get_hero_prompt_strategy


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
        hero_prompt_scheme: str = "b",
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
            {"role": "system", "content": get_hero_prompt_strategy(hero_prompt_scheme).vision_system_prompt},
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
