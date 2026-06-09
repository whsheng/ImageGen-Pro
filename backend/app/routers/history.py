from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_container, require_global_api_key
from app.schemas import HistoryRegenerateRequest
from app.services.generator import ProviderError
from app.services.key_manager import NoAvailableKeyError

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(require_global_api_key)])


@router.get("")
async def list_history(container=Depends(get_container)):
    return {"items": container.history_repo.list_recent()}


@router.delete("/{history_id}")
async def delete_history(history_id: int, container=Depends(get_container)):
    deleted = container.history_manager.delete_entry(history_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History not found")
    return {"ok": True}


@router.post("/{history_id}/regenerate")
async def regenerate_history(
    history_id: int,
    payload: HistoryRegenerateRequest,
    request: Request,
    container=Depends(get_container),
):
    try:
        result = await container.history_manager.regenerate(
            history_id,
            public_base_url=str(request.base_url).rstrip("/"),
            auto_translate=payload.auto_translate,
            model_override=payload.model,
        )
    except NoAvailableKeyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History not found")
    return result
