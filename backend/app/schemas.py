from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ImageGenerateRequest(BaseModel):
    model: str | None = None
    prompt: str = ""
    template_id: int | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    n: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024", pattern=r"^\d{2,4}x\d{2,4}$")
    auto_translate: bool = True

    @model_validator(mode="after")
    def validate_prompt(self) -> "ImageGenerateRequest":
        if not self.prompt.strip() and self.template_id is None:
            raise ValueError("prompt or template_id is required")
        return self


class OpenAIImageGenerateRequest(BaseModel):
    model: str | None = None
    prompt: str
    n: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024", pattern=r"^\d{2,4}x\d{2,4}$")
    response_format: Literal["url", "b64_json"] | None = None

    @model_validator(mode="after")
    def validate_prompt(self) -> "OpenAIImageGenerateRequest":
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        return self


class TemplateCreateRequest(BaseModel):
    name: str
    description: str = ""
    template: str
    category: str = ""
    preview_image_path: str = ""


class TemplateUpdateRequest(BaseModel):
    name: str
    description: str = ""
    template: str
    category: str = ""
    preview_image_path: str = ""


class HistoryRegenerateRequest(BaseModel):
    model: str | None = None
    auto_translate: bool = False
