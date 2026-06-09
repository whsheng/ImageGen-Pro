from __future__ import annotations

import re

import httpx

from app.services.key_manager import ConfigStore


class TranslationService:
    cjk_pattern = re.compile(r"[\u3400-\u9FFF]")

    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store
        self.client = httpx.AsyncClient(timeout=30.0)

    async def translate(self, prompt: str, enabled: bool = True) -> str:
        if not enabled or not self.contains_cjk(prompt):
            return prompt

        config = self.config_store.read().translation
        if not config.enabled:
            return prompt
        if config.provider == "mock":
            return prompt
        if not config.api_base or not config.api_key or not config.model:
            return prompt

        try:
            response = await self.client.post(
                f"{config.api_base.rstrip('/')}{config.chat_path}",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.model,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Translate Chinese image prompts into concise, production-ready English prompts. "
                                "Return only the translated prompt."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"].strip() or prompt
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return prompt

    @classmethod
    def contains_cjk(cls, prompt: str) -> bool:
        return bool(cls.cjk_pattern.search(prompt))

    async def aclose(self) -> None:
        await self.client.aclose()
