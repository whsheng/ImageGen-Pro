from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KeyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    key: str
    status: Literal["active", "cooling", "invalid"] = "active"
    cooling_until: datetime | None = None
    consecutive_failures: int = 0
    last_used: datetime | None = None
    last_success_at: datetime | None = None
    quota_remaining_percent: int | None = Field(default=None, ge=0, le=100)
    last_error: str | None = None


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    display_name: str
    provider: Literal["mock", "openai_compatible", "gemini_native", "qwen_native", "wuli_native"] = "mock"
    api_base: str = ""
    model_name: str | None = None
    generate_path: str = "/images/generations"
    timeout_seconds: int = 120
    keys: list[KeyConfig] = Field(default_factory=list)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class TranslationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    provider: Literal["mock", "openai_compatible"] = "mock"
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    chat_path: str = "/chat/completions"
    timeout_seconds: int = 30


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    global_api_key: str = "change-me"
    default_model: str = "agens"
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    models: dict[str, ModelConfig] = Field(default_factory=dict)


def _placeholder_key(key_id: str) -> KeyConfig:
    return KeyConfig(id=key_id, key="replace-with-real-key", quota_remaining_percent=100)


def build_default_config() -> AppConfig:
    return AppConfig(
        models={
            "agens": ModelConfig(
                display_name="Agens Image",
                provider="mock",
                api_base="https://replace-with-agens-endpoint",
                model_name="replace-with-agens-model",
                keys=[_placeholder_key("agens-01"), _placeholder_key("agens-02")],
            ),
            "gemini": ModelConfig(
                display_name="Gemini 2.5 Flash Image",
                provider="mock",
                api_base="https://generativelanguage.googleapis.com/v1beta",
                model_name="gemini-2.5-flash-image",
                keys=[_placeholder_key("gemini-01")],
            ),
            "openai": ModelConfig(
                display_name="OpenAI Image",
                provider="mock",
                api_base="https://api.openai.com/v1",
                model_name="gpt-image-2",
                provider_options={"request_body": {"output_format": "png"}},
                keys=[_placeholder_key("openai-01")],
            ),
            "qwen": ModelConfig(
                display_name="Qwen Image",
                provider="mock",
                api_base="https://replace-with-qwen-endpoint",
                model_name="qwen-image-2.0-pro",
                keys=[_placeholder_key("qwen-01")],
            ),
            "wuli": ModelConfig(
                display_name="WuLi Image",
                provider="mock",
                api_base="https://platform.wuli.art/api/v1/platform",
                model_name="Qwen Image Turbo",
                provider_options={"optimize_prompt": True, "poll_interval_seconds": 3, "poll_timeout_seconds": 180},
                keys=[_placeholder_key("wuli-01")],
            ),
        }
    )
