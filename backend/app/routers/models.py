from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_container, require_global_api_key

router = APIRouter(prefix="/api", tags=["models"], dependencies=[Depends(require_global_api_key)])


@router.get("/models")
async def list_models(container=Depends(get_container)):
    return container.key_manager.get_models_overview()
