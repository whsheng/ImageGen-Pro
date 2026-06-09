from __future__ import annotations

from pathlib import Path

from app.db.history import HistoryRepository
from app.services.generator import ImageGenerator


class HistoryManager:
    def __init__(self, history_repo: HistoryRepository, generator: ImageGenerator) -> None:
        self.history_repo = history_repo
        self.generator = generator

    def delete_entry(self, history_id: int) -> bool:
        record = self.history_repo.get(history_id)
        if record is None:
            return False

        for image in record.get("image_paths", []):
            path = image.get("path", "")
            if not path:
                continue
            file_path = Path(path)
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                # Best effort cleanup; history deletion should still proceed.
                pass

        return self.history_repo.delete(history_id)

    async def regenerate(
        self,
        history_id: int,
        *,
        public_base_url: str,
        auto_translate: bool = False,
        model_override: str | None = None,
    ) -> dict | None:
        record = self.history_repo.get(history_id)
        if record is None:
            return None

        return await self.generator.generate(
            model_name=model_override or record["model"],
            prompt=record["prompt"],
            count=record["n"],
            size=record["size"],
            public_base_url=public_base_url,
            auto_translate=auto_translate,
        )
