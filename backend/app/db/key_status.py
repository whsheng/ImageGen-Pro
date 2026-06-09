from __future__ import annotations

from app.db.sqlite_db import Database


class KeyStatusRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def replace_snapshot(self, records: list[dict]) -> None:
        with self.db.connect() as connection:
            connection.execute("DELETE FROM key_status")
            for record in records:
                connection.execute(
                    """
                    INSERT INTO key_status (
                        key_id, model, status, consecutive_failures,
                        cooling_until, last_success_at, last_used,
                        quota_remaining_percent, last_error, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["key_id"],
                        record["model"],
                        record["status"],
                        record["consecutive_failures"],
                        record["cooling_until"],
                        record["last_success_at"],
                        record["last_used"],
                        record["quota_remaining_percent"],
                        record["last_error"],
                        record["updated_at"],
                    ),
                )
            connection.commit()

    def list_all(self) -> list[dict]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM key_status
                ORDER BY model ASC, key_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

