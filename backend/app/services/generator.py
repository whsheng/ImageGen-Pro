from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import mimetypes
import re
import time
import uuid
from fractions import Fraction
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config_models import KeyConfig, ModelConfig
from app.db.history import HistoryRepository
from app.services.key_manager import KeyManager, NoAvailableKeyError
from app.services.translator import TranslationService


class ProviderError(RuntimeError):
    def __init__(self, message: str, kind: str = "provider_error") -> None:
        super().__init__(message)
        self.kind = kind


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="rate_limit")


class ProviderQuotaError(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="quota_exceeded")


@dataclass(slots=True)
class ProviderArtifact:
    content: bytes
    extension: str
    mime_type: str


@dataclass(slots=True)
class ProviderGenerationResult:
    artifacts: list[ProviderArtifact]
    quota_remaining_percent: int | None = None


SUPPORTED_GEMINI_ASPECT_RATIOS = [
    (1, 1),
    (1, 4),
    (1, 8),
    (2, 3),
    (3, 2),
    (3, 4),
    (4, 1),
    (4, 3),
    (4, 5),
    (5, 4),
    (8, 1),
    (9, 16),
    (16, 9),
    (21, 9),
]
GEMINI_IMAGE_SIZES = [
    (512, "0.5K"),
    (1024, "1K"),
    (2048, "2K"),
    (4096, "4K"),
]


class MockImageProvider:
    async def generate(
        self,
        *,
        prompt: str,
        count: int,
        size: str,
        **_: object,
    ) -> ProviderGenerationResult:
        width, height = self._parse_size(size)
        return ProviderGenerationResult(
            artifacts=[
                ProviderArtifact(
                    content=self._build_svg(width, height, f"{prompt}:{index}"),
                    extension="svg",
                    mime_type="image/svg+xml",
                )
                for index in range(count)
            ]
        )

    def _parse_size(self, size: str) -> tuple[int, int]:
        match = re.fullmatch(r"(\d{2,4})x(\d{2,4})", size)
        if not match:
            raise ProviderError(f"Unsupported size '{size}'")
        return int(match.group(1)), int(match.group(2))

    def _build_svg(self, width: int, height: int, seed_text: str) -> bytes:
        seed = hashlib.sha256(seed_text.encode("utf-8")).digest()
        base = f"#{seed[0]:02x}{seed[1]:02x}{seed[2]:02x}"
        accent = f"#{seed[3]:02x}{seed[4]:02x}{seed[5]:02x}"
        label = html.escape(seed_text[:36], quote=True)
        svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{base}" />
      <stop offset="100%" stop-color="{accent}" />
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" rx="24" fill="url(#bg)" />
  <rect x="{width * 0.08:.1f}" y="{height * 0.08:.1f}" width="{width * 0.84:.1f}" height="{height * 0.84:.1f}" rx="18"
        fill="rgba(255,255,255,0.18)" stroke="rgba(255,255,255,0.4)" />
  <text x="50%" y="46%" text-anchor="middle" fill="white"
        font-size="{max(18, min(width, height) // 11)}" font-family="Arial, sans-serif">ImageGen Pro</text>
  <text x="50%" y="58%" text-anchor="middle" fill="rgba(255,255,255,0.92)"
        font-size="{max(12, min(width, height) // 20)}" font-family="Arial, sans-serif">{label}</text>
</svg>
""".strip()
        return svg.encode("utf-8")


class OpenAICompatibleProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def generate(
        self,
        *,
        alias: str,
        model_config: ModelConfig,
        key_config: KeyConfig,
        prompt: str,
        count: int,
        size: str,
    ) -> ProviderGenerationResult:
        if not model_config.api_base:
            raise ProviderError(f"Model '{alias}' is missing api_base")
        if not key_config.key or key_config.key == "replace-with-real-key":
            raise ProviderError(f"Key '{key_config.id}' is not configured")

        headers, params = self._build_auth(model_config, key_config)
        response = await self.client.post(
            f"{model_config.api_base.rstrip('/')}{model_config.generate_path}",
            headers=headers,
            params=params,
            json=self._build_request_body(model_config, alias, prompt, count, size),
            timeout=model_config.timeout_seconds,
        )

        if response.status_code >= 400:
            raise_provider_http_error(response)

        payload = response.json()
        artifacts: list[ProviderArtifact] = []
        for item in payload.get("data", []):
            if item.get("b64_json"):
                artifacts.append(
                    ProviderArtifact(
                        content=base64.b64decode(item["b64_json"]),
                        extension="png",
                        mime_type="image/png",
                    )
                )
                continue
            if item.get("url"):
                artifacts.append(await self._download_artifact(item["url"]))

        if not artifacts:
            raise ProviderError("Provider returned no image data")
        return ProviderGenerationResult(
            artifacts=artifacts,
            quota_remaining_percent=extract_quota_remaining_percent(
                model_config.provider_options,
                response,
                payload,
            ),
        )

    def _build_auth(self, model_config: ModelConfig, key_config: KeyConfig) -> tuple[dict, dict]:
        options = model_config.provider_options or {}
        auth_mode = str(options.get("auth_mode", "bearer"))
        auth_header = str(options.get("auth_header", "Authorization"))
        auth_prefix = str(options.get("auth_prefix", "Bearer "))
        headers = {"Content-Type": "application/json"}
        headers.update(_string_dict(options.get("headers")))
        params = _string_dict(options.get("query"))

        if auth_mode == "bearer":
            headers[auth_header] = f"{auth_prefix}{key_config.key}"
        elif auth_mode == "header":
            headers[auth_header] = key_config.key
        elif auth_mode == "query":
            params[str(options.get("api_key_query_name", "api_key"))] = key_config.key
        elif auth_mode == "none":
            pass
        else:
            raise ProviderError(f"Unsupported auth_mode '{auth_mode}' for openai_compatible provider")
        return headers, params

    def _build_request_body(
        self,
        model_config: ModelConfig,
        alias: str,
        prompt: str,
        count: int,
        size: str,
    ) -> dict:
        options = model_config.provider_options or {}
        request_body = {
            str(options.get("prompt_field", "prompt")): prompt,
            str(options.get("count_field", "n")): count,
            str(options.get("size_field", "size")): size,
        }
        if not bool(options.get("omit_model", False)):
            request_body[str(options.get("model_field", "model"))] = model_config.model_name or alias
        request_body.update(_dict_copy(options.get("request_body")))
        return request_body

    async def _download_artifact(self, url: str) -> ProviderArtifact:
        response = await self.client.get(url)
        response.raise_for_status()
        mime_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
        extension = mimetypes.guess_extension(mime_type) or Path(urlparse(url).path).suffix or ".png"
        return ProviderArtifact(
            content=response.content,
            extension=extension.lstrip("."),
            mime_type=mime_type,
        )


class GeminiNativeProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def generate(
        self,
        *,
        alias: str,
        model_config: ModelConfig,
        key_config: KeyConfig,
        prompt: str,
        count: int,
        size: str,
    ) -> ProviderGenerationResult:
        if not model_config.api_base:
            raise ProviderError(f"Model '{alias}' is missing api_base")
        if not key_config.key or key_config.key == "replace-with-real-key":
            raise ProviderError(f"Key '{key_config.id}' is not configured")

        artifacts = []
        quota_remaining_percent = None
        for _ in range(count):
            response = await self.client.post(
                self._build_endpoint(model_config, alias),
                headers={
                    "x-goog-api-key": key_config.key,
                    "Content-Type": "application/json",
                    **_string_dict((model_config.provider_options or {}).get("headers")),
                },
                json=self._build_request_body(model_config, alias, prompt, size),
                timeout=model_config.timeout_seconds,
            )
            if response.status_code >= 400:
                raise_provider_http_error(response)
            payload = response.json()
            artifacts.extend(self._extract_artifacts(payload))
            response_quota = extract_quota_remaining_percent(
                model_config.provider_options,
                response,
                payload,
            )
            if response_quota is not None:
                quota_remaining_percent = response_quota

        return ProviderGenerationResult(
            artifacts=artifacts,
            quota_remaining_percent=quota_remaining_percent,
        )

    def _build_endpoint(self, model_config: ModelConfig, alias: str) -> str:
        model_name = model_config.model_name or alias
        return f"{model_config.api_base.rstrip('/')}/models/{model_name}:generateContent"

    def _build_request_body(self, model_config: ModelConfig, alias: str, prompt: str, size: str) -> dict:
        options = model_config.provider_options or {}
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ]
                }
            ]
        }
        generation_config = _dict_copy(options.get("generation_config"))
        image_config = _dict_copy(generation_config.get("imageConfig"))
        image_config.update(self._derive_image_options(model_config, alias, size))
        if image_config:
            generation_config["imageConfig"] = image_config

        if "responseModalities" not in generation_config:
            generation_config["responseModalities"] = options.get("response_modalities", ["IMAGE"])

        if generation_config:
            body["generationConfig"] = generation_config
        body.update(_dict_copy(options.get("request_body")))
        return body

    def _derive_image_options(self, model_config: ModelConfig, alias: str, size: str) -> dict:
        width, height = parse_size(size)
        aspect_ratio = nearest_gemini_aspect_ratio(width, height)
        image_options = {"aspectRatio": aspect_ratio}
        model_name = (model_config.model_name or alias).lower()
        if model_name.startswith("gemini-3") or model_name.startswith("gemini-2.5"):
            image_options["imageSize"] = nearest_gemini_image_size(width, height)
        return image_options

    def _extract_artifacts(self, payload: dict) -> list[ProviderArtifact]:
        artifacts = []
        text_parts = []
        for candidate in payload.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                    extension = mimetypes.guess_extension(mime_type) or ".png"
                    artifacts.append(
                        ProviderArtifact(
                            content=base64.b64decode(inline["data"]),
                            extension=extension.lstrip("."),
                            mime_type=mime_type,
                        )
                    )
                elif part.get("text"):
                    text_parts.append(str(part["text"]))

        if not artifacts:
            suffix = f" Response text: {' '.join(text_parts)}" if text_parts else ""
            raise ProviderError(f"Gemini returned no image data.{suffix}".strip())
        return artifacts


class QwenNativeProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def generate(
        self,
        *,
        alias: str,
        model_config: ModelConfig,
        key_config: KeyConfig,
        prompt: str,
        count: int,
        size: str,
    ) -> ProviderGenerationResult:
        if not model_config.api_base:
            raise ProviderError(f"Model '{alias}' is missing api_base")
        if not key_config.key or key_config.key == "replace-with-real-key":
            raise ProviderError(f"Key '{key_config.id}' is not configured")

        response = await self.client.post(
            f"{model_config.api_base.rstrip('/')}/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": f"Bearer {key_config.key}",
                "Content-Type": "application/json",
                **_string_dict((model_config.provider_options or {}).get("headers")),
            },
            json=self._build_request_body(model_config, alias, prompt, count, size),
            timeout=model_config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise_provider_http_error(response)

        payload = response.json()
        artifacts = await self._extract_artifacts(payload)
        return ProviderGenerationResult(
            artifacts=artifacts,
            quota_remaining_percent=extract_quota_remaining_percent(
                model_config.provider_options,
                response,
                payload,
            ),
        )

    def _build_request_body(
        self,
        model_config: ModelConfig,
        alias: str,
        prompt: str,
        count: int,
        size: str,
    ) -> dict:
        width, height = parse_size(size)
        options = model_config.provider_options or {}
        parameters = {
            "size": f"{width}*{height}",
            "n": count,
        }
        parameters.update({"prompt_extend": True, "watermark": False})
        parameters.update(_dict_copy(options.get("parameters")))
        body = {
            "model": model_config.model_name or alias,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": prompt,
                            }
                        ],
                    }
                ]
            },
            "parameters": parameters,
        }
        body.update(_dict_copy(options.get("request_body")))
        return body

    async def _extract_artifacts(self, payload: dict) -> list[ProviderArtifact]:
        artifacts: list[ProviderArtifact] = []
        choices = _json_path_get(payload, "output.choices")
        if not isinstance(choices, list):
            raise ProviderError("Qwen returned no image choices")

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            content = _json_path_get(choice, "message.content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                url = item.get("image")
                if url:
                    artifacts.append(await self._download_artifact(str(url)))

        if not artifacts:
            raise ProviderError("Qwen returned no downloadable image urls")
        return artifacts

    async def _download_artifact(self, url: str) -> ProviderArtifact:
        response = await self.client.get(url)
        response.raise_for_status()
        mime_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
        extension = mimetypes.guess_extension(mime_type) or Path(urlparse(url).path).suffix or ".png"
        return ProviderArtifact(
            content=response.content,
            extension=extension.lstrip("."),
            mime_type=mime_type,
        )


class WuliNativeProvider:
    terminal_statuses = {"SUCCEED", "FAILED", "REVIEWFAILED", "TIMEOUT", "CANCELLED"}

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def generate(
        self,
        *,
        alias: str,
        model_config: ModelConfig,
        key_config: KeyConfig,
        prompt: str,
        count: int,
        size: str,
    ) -> ProviderGenerationResult:
        if not model_config.api_base:
            raise ProviderError(f"Model '{alias}' is missing api_base")
        if not key_config.key or key_config.key == "replace-with-real-key":
            raise ProviderError(f"Key '{key_config.id}' is not configured")

        if count != 1:
            raise ProviderError("Wuli currently supports only n=1 in this project")

        options = model_config.provider_options or {}
        response = await self.client.post(
            f"{model_config.api_base.rstrip('/')}/predict/submit",
            headers={
                "Authorization": f"Bearer {key_config.key}",
                "Content-Type": "application/json",
                **_string_dict(options.get("headers")),
            },
            json=self._build_request_body(model_config, alias, prompt, size),
            timeout=model_config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise_provider_http_error(response)

        payload = response.json()
        if payload.get("success") is False:
            raise ProviderError(self._extract_message(payload))
        record_id = _json_path_get(payload, "data.recordId")
        if not record_id:
            raise ProviderError("Wuli submit returned no recordId")

        poll_interval = self._coerce_positive_float(options.get("poll_interval_seconds"), 3.0)
        poll_timeout = self._coerce_positive_float(options.get("poll_timeout_seconds"), 180.0)
        query_payload = await self._poll_result(
            api_base=model_config.api_base,
            api_key=key_config.key,
            record_id=str(record_id),
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
            timeout=model_config.timeout_seconds,
        )
        artifacts = await self._extract_artifacts(query_payload)
        return ProviderGenerationResult(artifacts=artifacts)

    def _build_request_body(self, model_config: ModelConfig, alias: str, prompt: str, size: str) -> dict:
        width, height = parse_size(size)
        options = model_config.provider_options or {}
        body = {
            "modelName": model_config.model_name or alias,
            "prompt": prompt,
            "mediaType": "IMAGE",
            "predictType": "TXT_2_IMG",
            "aspectRatio": nearest_wuli_aspect_ratio(width, height),
            "resolution": nearest_wuli_resolution(width, height),
            "n": 1,
            "optimizePrompt": bool(options.get("optimize_prompt", True)),
        }
        body.update(_dict_copy(options.get("request_body")))
        return body

    async def _poll_result(
        self,
        *,
        api_base: str,
        api_key: str,
        record_id: str,
        poll_interval: float,
        poll_timeout: float,
        timeout: int,
    ) -> dict:
        deadline = time.monotonic() + poll_timeout
        last_payload: dict | None = None
        while time.monotonic() < deadline:
            response = await self.client.get(
                f"{api_base.rstrip('/')}/predict/query",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"recordId": record_id},
                timeout=timeout,
            )
            if response.status_code >= 400:
                raise_provider_http_error(response)
            payload = response.json()
            if payload.get("success") is False:
                raise ProviderError(self._extract_message(payload))
            last_payload = payload
            status = _json_path_get(payload, "data.recordStatus")
            if status in self.terminal_statuses:
                if status != "SUCCEED":
                    raise ProviderError(f"Wuli task ended with status={status}: {self._extract_message(payload)}")
                return payload
            await self._sleep(poll_interval)

        raise ProviderError(
            f"Wuli polling timed out after {poll_timeout}s. Last payload: "
            f"{json.dumps(last_payload or {}, ensure_ascii=False)}"
        )

    async def _extract_artifacts(self, payload: dict) -> list[ProviderArtifact]:
        results = _json_path_get(payload, "data.results")
        if not isinstance(results, list):
            raise ProviderError("Wuli returned no results array")

        artifacts: list[ProviderArtifact] = []
        for item in results:
            if not isinstance(item, dict) or item.get("status") != "SUCCEED":
                continue
            image_url = item.get("imageUrl")
            if image_url:
                artifacts.append(await self._download_artifact(str(image_url)))

        if not artifacts:
            raise ProviderError("Wuli returned no downloadable image urls")
        return artifacts

    async def _download_artifact(self, url: str) -> ProviderArtifact:
        response = await self.client.get(url)
        response.raise_for_status()
        mime_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        extension = mimetypes.guess_extension(mime_type) or Path(urlparse(url).path).suffix or ".jpg"
        return ProviderArtifact(
            content=response.content,
            extension=extension.lstrip("."),
            mime_type=mime_type,
        )

    async def _sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def _coerce_positive_float(self, value: object, default: float) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return default
        return result if result > 0 else default

    def _extract_message(self, payload: dict) -> str:
        return str(payload.get("msg") or payload.get("message") or json.dumps(payload, ensure_ascii=False))


def parse_size(size: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", size)
    if not match:
        raise ProviderError(f"Unsupported size '{size}'")
    return int(match.group(1)), int(match.group(2))


def nearest_gemini_aspect_ratio(width: int, height: int) -> str:
    target = width / height
    ratio = min(
        SUPPORTED_GEMINI_ASPECT_RATIOS,
        key=lambda item: abs((item[0] / item[1]) - target),
    )
    return f"{ratio[0]}:{ratio[1]}"


def nearest_gemini_image_size(width: int, height: int) -> str:
    maximum = max(width, height)
    _, label = min(
        GEMINI_IMAGE_SIZES,
        key=lambda item: (abs(item[0] - maximum), -item[0]),
    )
    return label


def nearest_wuli_aspect_ratio(width: int, height: int) -> str:
    target = width / height
    supported = [
        (1, 1),
        (4, 3),
        (3, 2),
        (16, 9),
        (21, 9),
        (3, 4),
        (2, 3),
        (9, 16),
        (9, 21),
    ]
    ratio = min(supported, key=lambda item: abs((item[0] / item[1]) - target))
    return f"{ratio[0]}:{ratio[1]}"


def nearest_wuli_resolution(width: int, height: int) -> str:
    maximum = max(width, height)
    if maximum <= 1024:
        return "1K"
    if maximum <= 2048:
        return "2K"
    if maximum <= 3072:
        return "3K"
    return "4K"


def raise_provider_http_error(response: httpx.Response) -> None:
    message = response.text
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error", payload)
            if isinstance(error, dict):
                message = error.get("message") or error.get("code") or json.dumps(error, ensure_ascii=False)
            elif isinstance(error, str):
                message = error
    except ValueError:
        pass
    lower_message = message.lower()
    if "quota" in lower_message or "insufficient" in lower_message:
        raise ProviderQuotaError(message)
    if response.status_code == 429 or "rate limit" in lower_message:
        raise ProviderRateLimitError(message)
    raise ProviderError(f"Provider error {response.status_code}: {message}")


def _dict_copy(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def extract_quota_remaining_percent(
    provider_options: dict | None,
    response: httpx.Response,
    payload: dict | None,
) -> int | None:
    options = provider_options or {}
    multiplier = _coerce_multiplier(options.get("quota_remaining_percent_multiplier"))
    header_name = options.get("quota_remaining_percent_header")
    if header_name:
        value = _normalize_quota_remaining_percent(response.headers.get(str(header_name)), multiplier)
        if value is not None:
            return value

    json_path = options.get("quota_remaining_percent_json_path")
    if json_path and isinstance(payload, dict):
        raw_value = _json_path_get(payload, str(json_path))
        value = _normalize_quota_remaining_percent(raw_value, multiplier)
        if value is not None:
            return value

    return None


def _coerce_multiplier(value: object) -> float:
    try:
        multiplier = float(value)
    except (TypeError, ValueError):
        return 1.0
    return multiplier if math.isfinite(multiplier) else 1.0


def _normalize_quota_remaining_percent(raw_value: object, multiplier: float) -> int | None:
    if raw_value is None or isinstance(raw_value, bool):
        return None

    try:
        numeric = float(str(raw_value).strip()) * multiplier
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric):
        return None
    if numeric < 0 or numeric > 100:
        return None
    return int(round(numeric))


def _json_path_get(payload: object, path: str) -> object:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


class ImageGenerator:
    def __init__(
        self,
        *,
        key_manager: KeyManager,
        history_repo: HistoryRepository,
        translator: TranslationService,
        output_dir: Path,
    ) -> None:
        self.key_manager = key_manager
        self.history_repo = history_repo
        self.translator = translator
        self.output_dir = Path(output_dir)
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=120.0)
        self.providers = {
            "mock": MockImageProvider(),
            "openai_compatible": OpenAICompatibleProvider(self.client),
            "gemini_native": GeminiNativeProvider(self.client),
            "qwen_native": QwenNativeProvider(self.client),
            "wuli_native": WuliNativeProvider(self.client),
        }

    async def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        count: int,
        size: str,
        public_base_url: str,
        auto_translate: bool,
    ) -> dict:
        translated_prompt = await self.translator.translate(prompt, enabled=auto_translate)
        attempted_keys: set[str] = set()
        available = self.key_manager.count_available_keys(model_name)
        if available == 0:
            raise NoAvailableKeyError(f"No active keys available for model '{model_name}'")

        errors: list[str] = []
        for _ in range(available):
            model_config, key_config = self.key_manager.select_next_key(model_name, exclude=attempted_keys)
            attempted_keys.add(key_config.id)
            provider = self.providers.get(model_config.provider)
            if provider is None:
                errors.append(f"{key_config.id}: unsupported provider '{model_config.provider}'")
                continue
            try:
                provider_result = await provider.generate(
                    alias=model_name,
                    model_config=model_config,
                    key_config=key_config,
                    prompt=translated_prompt,
                    count=count,
                    size=size,
                )
                stored_images = self._store_artifacts(provider_result.artifacts, public_base_url)
                history_id = self.history_repo.create(
                    prompt=prompt,
                    prompt_translated=translated_prompt,
                    model=model_name,
                    key_id=key_config.id,
                    image_count=len(stored_images),
                    image_records=stored_images,
                    size=size,
                )
                if provider_result.quota_remaining_percent is None:
                    self.key_manager.record_success(model_name, key_config.id)
                else:
                    self.key_manager.record_success(
                        model_name,
                        key_config.id,
                        quota_remaining_percent=provider_result.quota_remaining_percent,
                    )
                return {
                    "created": int(datetime.now(UTC).timestamp()),
                    "history_id": history_id,
                    "model": model_name,
                    "key_id": key_config.id,
                    "prompt": prompt,
                    "prompt_translated": translated_prompt,
                    "data": stored_images,
                }
            except ProviderError as error:
                self.key_manager.record_failure(model_name, key_config.id, error.kind, str(error))
                errors.append(f"{key_config.id}: {error}")
            except httpx.HTTPError as error:
                self.key_manager.record_failure(model_name, key_config.id, "provider_error", str(error))
                errors.append(f"{key_config.id}: {error}")

        raise ProviderError("; ".join(errors) or "All image providers failed")

    def _store_artifacts(self, artifacts: list[ProviderArtifact], public_base_url: str) -> list[dict]:
        date_dir = datetime.now().date().isoformat()
        output_dir = self.output_dir / date_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        stored = []
        for artifact in artifacts:
            file_name = f"{uuid.uuid4().hex}.{artifact.extension}"
            file_path = output_dir / file_name
            file_path.write_bytes(artifact.content)
            relative_path = f"static/outputs/{date_dir}/{file_name}"
            public_url = f"{public_base_url.rstrip('/')}/{relative_path}"
            stored.append(
                {
                    "url": public_url,
                    "path": str(file_path),
                    "relative_path": relative_path,
                    "mime_type": artifact.mime_type,
                }
            )
        return stored

    async def aclose(self) -> None:
        await self.client.aclose()
