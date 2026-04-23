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


def _strip_json_wrappers(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]
    if text.startswith("json"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.strip()


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]

    return text[start:]


def _parse_json_payload(text: str) -> dict:
    normalized = _strip_json_wrappers(text)
    candidates: list[str] = []
    for candidate in (
        normalized,
        _extract_first_json_object(normalized),
        _fix_truncated_json(_extract_first_json_object(normalized)),
        _fix_truncated_json(normalized),
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise json.JSONDecodeError("No JSON content found", normalized, 0)


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

        base_messages = [
            {"role": "system", "content": get_hero_prompt_strategy(hero_prompt_scheme).vision_system_prompt},
            {"role": "user", "content": user_content},
        ]

        data = None
        last_exc: json.JSONDecodeError | None = None
        last_content = ""
        for attempt in range(2):
            messages = list(base_messages)
            if attempt > 0:
                messages.append(
                    {
                        "role": "user",
                        "content": "上一次输出不是合法 JSON。请只返回一个可被 json.loads 直接解析的 JSON 对象，不要 markdown，不要解释，不要补充说明。",
                    }
                )

            content = await self.client.chat_completion(
                messages=messages,
                temperature=0.1 if attempt > 0 else 0.3,
                max_tokens=16384,
            )
            last_content = content

            try:
                data = _parse_json_payload(content)
                break
            except json.JSONDecodeError as exc:
                last_exc = exc
                print(f"[ERROR] Vision LLM returned invalid JSON on attempt {attempt + 1}: {exc}")
                print(f"[ERROR] Raw content (first 2000 chars): {_strip_json_wrappers(content)[:2000]}")

        if data is None:
            raise RuntimeError(
                f"视觉分析返回的 JSON 解析失败。请检查 LLM 输出格式。原始错误: {last_exc}. 响应片段: {_strip_json_wrappers(last_content)[:300]}"
            ) from last_exc

        # Inject source image path for downstream traceability
        data["source_images"] = [{"index": 1, "path": str(image_path.resolve()), "role": "primary"}]
        return data
