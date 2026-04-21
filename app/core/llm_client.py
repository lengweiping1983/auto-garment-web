"""Vision LLM client wrapper."""
import base64
from pathlib import Path

from app.config import settings


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
            extra_body={"enable_thinking": False},
        )
        return response.choices[0].message.content or ""

