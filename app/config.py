"""Application configuration using Pydantic Settings."""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "kimi-coding"
    llm_protocol: str = "openai"  # "openai" or "anthropic"
    llm_api_key: str = ""
    llm_model: str = "kimi-for-coding"
    llm_base_url: str = "https://api.kimi.com/coding"

    # Neo AI
    neodomain_base_url: str = "https://story.neodomain.cn/agent/ai-image-generation"
    neodomain_access_token: str = ""
    neodomain_default_model: str = "doubao-seedream-5-0-260128"
    neodomain_default_size: str = "2K"

    # Test mode: skip AI generation and wait for manual uploads
    skip_ai_generation: bool = False

    # Render strategy: auto | stream | serial
    render_mode: str = "auto"
    low_memory_serial_render_threshold_gb: float = 2.5

    @property
    def resolved_neodomain_access_token(self) -> str:
        """Return token from NEODOMAIN_ACCESS_TOKEN or fall back to NEODOMAIN_ACCESS_TOKEN."""
        # NEODOMAIN_ACCESS_TOKEN (from shell env) takes precedence
        env_token = os.environ.get("NEODOMAIN_ACCESS_TOKEN", "")
        if env_token:
            return env_token
        return self.neodomain_access_token

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
