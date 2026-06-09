from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.container import AppContainer, RuntimeSettings
from app.routers import admin, history, images, models, templates


def resolve_config_path(config_path: str | None = None, *, backend_dir: Path | None = None) -> Path:
    resolved_backend_dir = backend_dir or Path(__file__).resolve().parents[1]
    if config_path:
        return Path(config_path)

    env_path = os.getenv("IMAGEGEN_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    local_config_path = resolved_backend_dir / "config.local.json"
    if local_config_path.exists():
        return local_config_path

    return resolved_backend_dir / "config.json"


def _build_settings(
    config_path: str | None = None,
    db_path: str | None = None,
    output_dir: str | None = None,
    frontend_dir: str | None = None,
) -> RuntimeSettings:
    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    static_dir = backend_dir / "static"
    resolved_output_dir = Path(output_dir or os.getenv("IMAGEGEN_OUTPUT_DIR") or static_dir / "outputs")
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        config_path=resolve_config_path(config_path, backend_dir=backend_dir),
        db_path=Path(db_path or os.getenv("IMAGEGEN_DB_PATH") or backend_dir / "imagegen.db"),
        static_dir=static_dir,
        output_dir=resolved_output_dir,
        output_mount_path="/static/outputs",
        frontend_dir=Path(frontend_dir or os.getenv("IMAGEGEN_FRONTEND_DIR") or project_root / "frontend"),
    )


def create_app(
    config_path: str | None = None,
    db_path: str | None = None,
    output_dir: str | None = None,
    frontend_dir: str | None = None,
) -> FastAPI:
    settings = _build_settings(config_path, db_path, output_dir, frontend_dir)
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container.initialize()
        app.state.container = container
        yield
        await container.aclose()

    app = FastAPI(
        title="ImageGen Pro",
        version="0.1.0",
        lifespan=lifespan,
        description="Unified image generation service with Web UI and OpenAI compatible API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(images.router)
    app.include_router(models.router)
    app.include_router(admin.router)
    app.include_router(templates.router)
    app.include_router(history.router)

    app.mount(settings.output_mount_path, StaticFiles(directory=str(settings.output_dir)), name="generated-images")
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    if settings.frontend_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(settings.frontend_dir), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root():
        if settings.frontend_dir.exists():
            return RedirectResponse(url="/ui")
        return {"name": "ImageGen Pro", "version": "0.1.0"}

    return app
