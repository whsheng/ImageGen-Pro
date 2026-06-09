from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.db.history import HistoryRepository
from app.db.key_status import KeyStatusRepository
from app.db.sqlite_db import Database
from app.db.templates import TemplateRepository
from app.services.generator import ImageGenerator
from app.services.history_manager import HistoryManager
from app.services.key_manager import ConfigStore, KeyManager
from app.services.translator import TranslationService


@dataclass(slots=True)
class RuntimeSettings:
    config_path: Path
    db_path: Path
    static_dir: Path
    output_dir: Path
    output_mount_path: str
    frontend_dir: Path


class AppContainer:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self.database = Database(settings.db_path)
        self.history_repo = HistoryRepository(self.database)
        self.template_repo = TemplateRepository(self.database)
        self.key_status_repo = KeyStatusRepository(self.database)
        self.config_store = ConfigStore(settings.config_path)
        self.key_manager = KeyManager(self.config_store, self.key_status_repo)
        self.translator = TranslationService(self.config_store)
        self.generator = ImageGenerator(
            key_manager=self.key_manager,
            history_repo=self.history_repo,
            translator=self.translator,
            output_dir=settings.output_dir,
        )
        self.history_manager = HistoryManager(self.history_repo, self.generator)

    def initialize(self) -> None:
        self.settings.static_dir.mkdir(parents=True, exist_ok=True)
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.config_store.ensure_exists()
        self._warn_on_insecure_defaults()
        self.database.initialize()
        self.template_repo.seed_defaults()
        self.key_manager.sync_key_statuses()

    async def aclose(self) -> None:
        await self.generator.aclose()
        await self.translator.aclose()

    def _warn_on_insecure_defaults(self) -> None:
        configured_key = os.getenv("IMAGEGEN_GLOBAL_API_KEY") or self.config_store.read().global_api_key
        if configured_key == "change-me":
            print(
                "WARNING: global_api_key is still 'change-me'. "
                "Set backend/config.local.json, backend/config.json, or IMAGEGEN_GLOBAL_API_KEY before exposing this service."
            )
