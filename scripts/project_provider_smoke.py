#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from app.application import create_app, resolve_config_path


PROMPT = "A minimalist product photo of a glossy red apple on a white studio background, soft shadow, high detail"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exercise project /v1/images/generations through ASGI.")
    parser.add_argument(
        "--models",
        default="openai,agens,qwen,wuli",
        help="Comma separated model aliases to test",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional summary output path",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Global API key used to call the app. Defaults to IMAGEGEN_GLOBAL_API_KEY or the resolved config file.",
    )
    parser.add_argument(
        "--config-path",
        default="",
        help="Optional config path passed to create_app. Defaults to IMAGEGEN_CONFIG_PATH or backend/config.local.json when present.",
    )
    return parser.parse_args()


def resolve_global_api_key(config_path_arg: str) -> str:
    env_key = os.getenv("IMAGEGEN_GLOBAL_API_KEY")
    if env_key:
        return env_key

    config_path = resolve_config_path(config_path_arg or None)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return str(payload.get("global_api_key", "change-me"))


async def run_case(models: list[str], *, api_key: str, config_path: str) -> dict:
    app = create_app(config_path=config_path or None)
    summary: dict[str, object] = {"results": {}, "errors": {}}
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for model in models:
                response = await client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "prompt": PROMPT,
                        "n": 1,
                        "size": "1024x1024",
                    },
                    timeout=300.0,
                )
                if response.status_code == 200:
                    summary["results"][model] = response.json()
                else:
                    summary["errors"][model] = {
                        "status_code": response.status_code,
                        "body": response.text,
                    }
    return summary


def main() -> int:
    args = parse_args()
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    api_key = args.api_key or resolve_global_api_key(args.config_path)
    summary = asyncio.run(run_case(models, api_key=api_key, config_path=args.config_path))
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
