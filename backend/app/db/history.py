from __future__ import annotations

import json
from datetime import datetime

from app.db.sqlite_db import Database


class HistoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self,
        *,
        prompt: str,
        prompt_translated: str | None,
        model: str,
        key_id: str,
        image_count: int,
        image_records: list[dict],
        size: str,
    ) -> int:
        created_at = datetime.now().isoformat(timespec="seconds")
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO generation_history (
                    prompt, prompt_translated, model, key_id,
                    image_count, image_paths, size, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt,
                    prompt_translated,
                    model,
                    key_id,
                    image_count,
                    json.dumps(image_records, ensure_ascii=False),
                    size,
                    created_at,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_recent(self, limit: int = 50) -> list[dict]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM generation_history
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, history_id: int) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM generation_history WHERE id = ?",
                (history_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def delete(self, history_id: int) -> bool:
        with self.db.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM generation_history WHERE id = ?",
                (history_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    def count_today(self) -> int:
        today = datetime.now().date().isoformat()
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM generation_history
                WHERE substr(created_at, 1, 10) = ?
                """,
                (today,),
            ).fetchone()
        return int(row["total"])

    def _row_to_record(self, row) -> dict:
        record = dict(row)
        raw_images = json.loads(record["image_paths"]) if record["image_paths"] else []
        images = []
        for item in raw_images:
            if isinstance(item, str):
                images.append({"path": item, "url": "", "relative_path": ""})
            elif isinstance(item, dict):
                images.append(
                    {
                        "path": item.get("path", ""),
                        "url": item.get("url", ""),
                        "relative_path": item.get("relative_path", ""),
                    }
                )
        record["image_paths"] = images
        record["thumbnail"] = images[0]["url"] if images else ""
        record["n"] = record["image_count"]
        return record
