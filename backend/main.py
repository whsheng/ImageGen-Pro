from __future__ import annotations

import os

import uvicorn

from app.application import create_app

app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )

