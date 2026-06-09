from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_container, require_global_api_key
from app.schemas import ImageGenerateRequest, OpenAIImageGenerateRequest
from app.services.generator import ProviderError
from app.services.key_manager import NoAvailableKeyError

router = APIRouter(tags=["images"])


def _public_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.post("/v1/images/generations", dependencies=[Depends(require_global_api_key)])
async def openai_generate_image(
    payload: OpenAIImageGenerateRequest,
    request: Request,
    container=Depends(get_container),
):
    model_name = payload.model or container.config_store.read().default_model
    try:
        result = await container.generator.generate(
            model_name=model_name,
            prompt=payload.prompt,
            count=payload.n,
            size=payload.size,
            public_base_url=_public_base_url(request),
            auto_translate=False,
        )
    except NoAvailableKeyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    response_format = payload.response_format or "url"
    if response_format == "b64_json":
        return {
            "created": result["created"],
            "data": [
                {"b64_json": base64.b64encode(Path(item["path"]).read_bytes()).decode("ascii")}
                for item in result["data"]
            ],
        }
    return {
        "created": result["created"],
        "data": [{"url": item["url"]} for item in result["data"]],
    }


@router.post("/api/images/generate")
async def generate_image(
    payload: ImageGenerateRequest,
    request: Request,
    _: None = Depends(require_global_api_key),
    container=Depends(get_container),
):
    prompt = payload.prompt.strip()
    if payload.template_id is not None:
        template = container.template_repo.get(payload.template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        try:
            prompt = template["template"].format(**payload.variables)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing template variable: {error.args[0]}",
            ) from error

    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt is required")

    model_name = payload.model or container.config_store.read().default_model
    try:
        result = await container.generator.generate(
            model_name=model_name,
            prompt=prompt,
            count=payload.n,
            size=payload.size,
            public_base_url=_public_base_url(request),
            auto_translate=payload.auto_translate,
        )
    except NoAvailableKeyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    return result
