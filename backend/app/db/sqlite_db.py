from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS generation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    prompt_translated TEXT,
    model VARCHAR(50) NOT NULL,
    key_id VARCHAR(50),
    image_count INTEGER DEFAULT 1,
    image_paths TEXT NOT NULL,
    size VARCHAR(20),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    template TEXT NOT NULL,
    category VARCHAR(50),
    preview_image_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_status (
    key_id VARCHAR(50) PRIMARY KEY,
    model VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    consecutive_failures INTEGER DEFAULT 0,
    cooling_until TEXT,
    last_success_at TEXT,
    last_used TEXT,
    quota_remaining_percent INTEGER,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_generation_history_created_at
    ON generation_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_updated_at
    ON prompt_templates(updated_at DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

