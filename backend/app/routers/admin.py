from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_container, require_global_api_key

router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_global_api_key)])


@router.get("/health")
async def health(container=Depends(get_container)):
    snapshot = container.key_manager.get_health_snapshot()
    snapshot["database"] = "ok"
    snapshot["config_path"] = str(container.settings.config_path)
    return snapshot


@router.get("/stats")
async def stats(request: Request, container=Depends(get_container)):
    config = container.config_store.read()
    history_count_today = container.history_repo.count_today()
    models = []
    current_key = None
    for model in container.key_manager.get_models_overview()["models"]:
        key = model.get("current_key")
        if model["id"] == config.default_model:
            current_key = key
        models.append(
            {
                "id": model["id"],
                "display_name": model["display_name"],
                "active_key_count": model["active_key_count"],
                "retry_ready_key_count": model.get("retry_ready_key_count", 0),
                "total_key_count": model["total_key_count"],
                "next_key_id": model["next_key_id"],
                "current_key": key,
                "average_quota_remaining_percent": _average_quota(model["keys"]),
            }
        )
    return {
        "today_generation_count": history_count_today,
        "current_model": config.default_model,
        "current_key": current_key,
        "current_key_id": current_key["id"] if current_key else None,
        "models": models,
        "public_base_url": str(request.base_url).rstrip("/"),
        "config_path": str(container.settings.config_path),
    }


def _average_quota(keys: list[dict]) -> int | None:
    values = [item["quota_remaining_percent"] for item in keys if item["quota_remaining_percent"] is not None]
    if not values:
        return None
    return round(sum(values) / len(values))
