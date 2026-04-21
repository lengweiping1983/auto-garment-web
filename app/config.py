"""Application configuration using Pydantic Settings."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "openai"
    llm_protocol: str = "openai"  # "openai" or "anthropic"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: str = "https://api.openai.com/v1"

    # Neo AI
    neo_ai_base_url: str = "https://story.neodomain.cn/agent/ai-image-generation"
    neo_ai_access_token: str = ""
    neo_ai_default_model: str = "gemini-3-pro-image-preview"
    neo_ai_default_size: str = "2K"

    # Test mode: skip AI generation and wait for manual uploads
    skip_ai_generation: bool = False

    @property
    def resolved_neo_ai_access_token(self) -> str:
        """Return token from NEODOMAIN_ACCESS_TOKEN or fall back to NEO_AI_ACCESS_TOKEN."""
        import os
        # NEODOMAIN_ACCESS_TOKEN (from shell env) takes precedence
        env_token = os.environ.get("NEODOMAIN_ACCESS_TOKEN", "")
        if env_token:
            return env_token
        return self.neo_ai_access_token

    # Storage
    storage_base_dir: Path = Path("./storage")
    max_task_age_days: int = 7

    # Templates
    templates_dir: Path = Path("./app/templates_data")

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 3000
    debug: bool = False


settings = Settings()
