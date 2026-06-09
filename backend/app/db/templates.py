from __future__ import annotations

from datetime import datetime

from app.db.sqlite_db import Database


DEFAULT_TEMPLATES = [
    {
        "name": "产品白底图",
        "description": "适合电商详情页的白底产品主图。",
        "template": "Product photography of {product_name}, pure white background, studio lighting, crisp shadow, ultra detailed",
        "category": "产品图",
        "preview_image_path": "",
    },
    {
        "name": "场景海报图",
        "description": "适合官网与社媒的场景式宣传图。",
        "template": "{product_name} placed in a premium lifestyle scene, cinematic lighting, elegant composition, realistic materials, advertising photography",
        "category": "场景图",
        "preview_image_path": "",
    },
    {
        "name": "社媒方图",
        "description": "适合朋友圈、小红书与短视频封面的方形配图。",
        "template": "{product_name} hero shot, bold composition, clean branding, social media campaign visual, modern commercial art direction",
        "category": "社媒图",
        "preview_image_path": "",
    },
]


class TemplateRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def seed_defaults(self) -> None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM prompt_templates").fetchone()
            if int(row["total"]) > 0:
                return
            now = datetime.now().isoformat(timespec="seconds")
            for item in DEFAULT_TEMPLATES:
                connection.execute(
                    """
                    INSERT INTO prompt_templates (
                        name, description, template, category,
                        preview_image_path, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["name"],
                        item["description"],
                        item["template"],
                        item["category"],
                        item["preview_image_path"],
                        now,
                        now,
                    ),
                )
            connection.commit()

    def list_all(self) -> list[dict]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM prompt_templates
                ORDER BY datetime(updated_at) DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, template_id: int) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM prompt_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        *,
        name: str,
        description: str,
        template: str,
        category: str,
        preview_image_path: str,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO prompt_templates (
                    name, description, template, category,
                    preview_image_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, description, template, category, preview_image_path, now, now),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(
        self,
        template_id: int,
        *,
        name: str,
        description: str,
        template: str,
        category: str,
        preview_image_path: str,
    ) -> bool:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE prompt_templates
                SET name = ?, description = ?, template = ?,
                    category = ?, preview_image_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, description, template, category, preview_image_path, now, template_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def delete(self, template_id: int) -> bool:
        with self.db.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM prompt_templates WHERE id = ?",
                (template_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

