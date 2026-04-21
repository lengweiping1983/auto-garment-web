"""Vision LLM client wrapper."""
import base64
import json
from pathlib import Path

from app.config import settings
from app.models.schemas import VisualElements


VISION_SYSTEM_PROMPT = """你是一位服装印花设计助理。观察用户上传的图片，提取以下信息并返回纯 JSON，不要任何解释文字。

必须返回的字段：
- palette: {primary: ["#hex", ...], secondary: [...], accent: [...], dark: [...]}
- style: {medium: "水彩/油画/数字等", mood: "氛围词", brush_quality: "笔触描述", pattern_density: "low|medium|high"}
- dominant_subject: "图片中最突出的主体描述（用于生成透明主图），必须包含身份、姿态、颜色、风格"
- motif_vocabulary: ["从图中提炼的 3-8 个小型可重复元素名称，如 tiny flowers, small leaves, dots"]
- fusion_rule: "一句话描述主图和纹理如何像同一套设计"

约束：
- 颜色必须从图片真实提取，不要编造
- 提示词用英文
- 不要输出 markdown 代码块"""


class LLMClient:
    def __init__(self):
        self.protocol = settings.llm_protocol.lower()
        self.model = settings.llm_model

        if self.protocol == "anthropic":
            from anthropic import AsyncAnthropic

            self._anthropic = AsyncAnthropic(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url if settings.llm_base_url else None,
            )
            self._openai = None
        else:
            from openai import AsyncOpenAI

            self._openai = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url if settings.llm_base_url else None,
            )
            self._anthropic = None

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _convert_messages_for_anthropic(messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Extract system prompt and convert OpenAI-style messages to Anthropic format."""
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                if isinstance(content, str):
                    system_prompt = content
                continue

            if role == "user" and isinstance(content, list):
                new_content = []
                for item in content:
                    item_type = item.get("type")
                    if item_type == "text":
                        new_content.append({"type": "text", "text": item.get("text", "")})
                    elif item_type == "image_url":
                        url = item["image_url"].get("url", "")
                        if url.startswith("data:"):
                            header, b64 = url.split(",", 1)
                            media_type = header.split(";")[0].replace("data:", "")
                            new_content.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": b64,
                                    },
                                }
                            )
                anthropic_messages.append({"role": "user", "content": new_content})
            else:
                anthropic_messages.append({"role": role, "content": content})

        return system_prompt, anthropic_messages

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Unified chat completion supporting both OpenAI and Anthropic protocols."""
        if self.protocol == "anthropic":
            system_prompt, anthropic_messages = self._convert_messages_for_anthropic(messages)
            response = await self._anthropic.messages.create(
                model=self.model,
                system=system_prompt,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.content[0].text if response.content else ""

        response = await self._openai.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def analyze_image(self, image_path: Path) -> VisualElements:
        """Single-call vision analysis returning structured visual elements."""
        b64_image = self._encode_image(image_path)
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

        messages = [
            {
                "role": "system",
                "content": VISION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "分析这张主题图，提取配色、风格、主体和小元素词汇。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                ],
            },
        ]

        content = await self.chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        # Clean markdown code blocks if any
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content.rsplit("\n", 1)[0]
        if content.startswith("json"):
            content = content.split("\n", 1)[1]

        data = json.loads(content.strip())
        return VisualElements(**data)
