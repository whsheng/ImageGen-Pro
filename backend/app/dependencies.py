from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.container import AppContainer


async def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def require_global_api_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    container: AppContainer = Depends(get_container),
) -> None:
    configured_key = os.getenv("IMAGEGEN_GLOBAL_API_KEY") or container.config_store.read().global_api_key
    provided_key = x_api_key

    if authorization and authorization.lower().startswith("bearer "):
        provided_key = authorization.split(" ", 1)[1].strip()

    if not configured_key or not provided_key or not secrets.compare_digest(configured_key, provided_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
