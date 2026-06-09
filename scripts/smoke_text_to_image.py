#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEYS_PATH = ROOT / "keys.txt"
DEFAULT_OUTPUT_ROOT = Path("/tmp/imagegen-pro-smoke")
DEFAULT_PROMPT = (
    "A minimalist product photo of a glossy red apple on a white studio background, "
    "soft shadow, high detail"
)

OPENAI_URL = "https://api.openai.com/v1/images/generations"
AGENS_URL = "https://apihub.agnes-ai.com/v1/images/generations"
QWEN_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
WULI_BASE = "https://platform.wuli.art/api/v1/platform"
WULI_TERMINAL_STATES = {"SUCCEED", "FAILED", "REVIEWFAILED", "TIMEOUT", "CANCELLED"}


class ApiError(RuntimeError):
    pass


@dataclass
class JsonResponse:
    status: int
    headers: dict[str, str]
    payload: dict
    raw_text: str


@dataclass
class ProviderSettings:
    values: list[str]
    options: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test text-to-image providers with real keys.")
    parser.add_argument(
        "--providers",
        default="openai,gemini,agens,qwen,wuli",
        help="Comma separated providers to test: openai,gemini,agens,qwen,wuli",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt used for generation",
    )
    parser.add_argument(
        "--keys-file",
        default=str(DEFAULT_KEYS_PATH),
        help="Path to keys.txt",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory to save raw responses and downloaded images",
    )
    parser.add_argument(
        "--wuli-poll-interval",
        type=float,
        default=3.0,
        help="Polling interval in seconds for Wuli async tasks",
    )
    parser.add_argument(
        "--wuli-timeout",
        type=float,
        default=180.0,
        help="Total wait timeout in seconds for Wuli async tasks",
    )
    parser.add_argument(
        "--gemini-models",
        default="gemini-3.1-flash-image,gemini-2.5-flash-image",
        help="Comma separated Gemini model candidates",
    )
    return parser.parse_args()


def load_keys(path: Path) -> dict[str, ProviderSettings]:
    if not path.exists():
        raise FileNotFoundError(f"keys file not found: {path}")

    provider_keys: dict[str, ProviderSettings] = {}
    current_provider: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("###"):
            current_provider = normalize_provider_name(line.removeprefix("###").strip())
            provider_keys.setdefault(current_provider, ProviderSettings(values=[], options={}))
            continue
        if current_provider is None:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            provider_keys[current_provider].options[normalize_option_name(key)] = value.strip()
            continue
        provider_keys[current_provider].values.append(line)
    return provider_keys


def normalize_provider_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def normalize_option_name(name: str) -> str:
    return normalize_provider_name(name)


def make_output_dir(path_arg: str) -> Path:
    if path_arg:
        output_dir = Path(path_arg).expanduser().resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_OUTPUT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def http_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    timeout: float = 300.0,
) -> JsonResponse:
    request_data = None
    request_headers = dict(headers or {})
    if payload is not None:
        request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(url, data=request_data, method=method.upper())
    for key, value in request_headers.items():
        request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_bytes = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw_bytes = exc.read()
        body = raw_bytes.decode("utf-8", errors="replace")
        raise ApiError(f"{method.upper()} {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"{method.upper()} {url} failed: {exc.reason}") from exc

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ApiError(f"{method.upper()} {url} returned non-JSON response: {raw_text[:500]}") from exc

    if not isinstance(parsed, dict):
        raise ApiError(f"{method.upper()} {url} returned unexpected JSON type: {type(parsed).__name__}")

    return JsonResponse(status=status, headers=response_headers, payload=parsed, raw_text=raw_text)


def download_file(url: str, destination: Path, stem: str) -> Path:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=300.0) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "image/png").split(";", 1)[0].strip()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"GET {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"GET {url} failed: {exc.reason}") from exc

    suffix = mimetypes.guess_extension(content_type) or Path(urllib.parse.urlparse(url).path).suffix or ".bin"
    file_path = destination / f"{stem}{suffix}"
    file_path.write_bytes(content)
    return file_path


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_key(key: str) -> str:
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:6]}...{key[-4:]}"


def ensure_success_flag(provider: str, payload: dict) -> None:
    success = payload.get("success")
    if success is False:
        code = payload.get("code")
        message = payload.get("msg") or payload.get("message") or json.dumps(payload, ensure_ascii=False)
        raise ApiError(f"{provider} returned success=false, code={code}, message={message}")


def run_agens(prompt: str, api_key: str, output_dir: Path) -> dict:
    provider_dir = output_dir / "agens"
    provider_dir.mkdir(parents=True, exist_ok=True)

    response = http_json(
        method="POST",
        url=AGENS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        payload={
            "model": "agnes-image-2.1-flash",
            "prompt": prompt,
            "size": "1024x1024",
            "extra_body": {"response_format": "url"},
        },
    )
    save_json(provider_dir / "response.json", response.payload)

    items = response.payload.get("data")
    if not isinstance(items, list) or not items:
        raise ApiError(f"Agens returned no data array: {response.raw_text}")
    image_url = items[0].get("url")
    if not image_url:
        raise ApiError(f"Agens returned no image url: {response.raw_text}")

    image_path = download_file(str(image_url), provider_dir, "result")
    return {
        "provider": "agens",
        "key": mask_key(api_key),
        "model": "agnes-image-2.1-flash",
        "image_url": image_url,
        "image_path": str(image_path),
        "response_path": str(provider_dir / "response.json"),
    }


def run_openai(prompt: str, api_key: str, output_dir: Path, api_base_url: str | None = None) -> dict:
    provider_dir = output_dir / "openai"
    provider_dir.mkdir(parents=True, exist_ok=True)
    model_candidates = ["gpt-image-2", "gpt-image-1.5", "gpt-image-1"]
    last_error: Exception | None = None
    endpoint = build_openai_images_endpoint(api_base_url)

    for model_name in model_candidates:
        try:
            response = http_json(
                method="POST",
                url=endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                payload={
                    "model": model_name,
                    "prompt": prompt,
                    "size": "1024x1024",
                    "output_format": "png",
                },
            )
            save_json(provider_dir / "response.json", response.payload)

            items = response.payload.get("data")
            if not isinstance(items, list) or not items:
                raise ApiError(f"OpenAI returned no data array: {response.raw_text}")
            b64_json = items[0].get("b64_json")
            if not b64_json:
                raise ApiError(f"OpenAI returned no b64_json image payload: {response.raw_text}")
            image_bytes = decode_base64_string(str(b64_json), "OpenAI image data")
            image_path = provider_dir / "result.png"
            image_path.write_bytes(image_bytes)
            return {
                "provider": "openai",
                "key": mask_key(api_key),
                "endpoint": endpoint,
                "model": model_name,
                "image_path": str(image_path),
                "response_path": str(provider_dir / "response.json"),
            }
        except Exception as exc:
            last_error = exc
            save_json(
                provider_dir / f"{model_name}.error.json",
                {
                    "model": model_name,
                    "error": str(exc),
                },
            )

    raise ApiError(f"OpenAI failed for all candidate models: {last_error}")


def build_openai_images_endpoint(api_base_url: str | None) -> str:
    if not api_base_url:
        return OPENAI_URL
    base = api_base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/images/generations"
    return f"{base}/v1/images/generations"


def run_gemini(prompt: str, api_key: str, output_dir: Path, model_candidates: list[str]) -> dict:
    provider_dir = output_dir / "gemini"
    provider_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for model_name in model_candidates:
        try:
            payload = {
                "contents": [
                    {
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "aspectRatio": "1:1",
                        "imageSize": "1K",
                    },
                },
            }

            response = http_json(
                method="POST",
                url=f"{GEMINI_BASE}/models/{model_name}:generateContent",
                headers={"x-goog-api-key": api_key},
                payload=payload,
            )
            save_json(provider_dir / "response.json", response.payload)

            image_bytes, mime_type = extract_gemini_image(response.payload)
            extension = mimetypes.guess_extension(mime_type) or ".png"
            image_path = provider_dir / f"result{extension}"
            image_path.write_bytes(image_bytes)
            return {
                "provider": "gemini",
                "key": mask_key(api_key),
                "model": model_name,
                "image_path": str(image_path),
                "mime_type": mime_type,
                "response_path": str(provider_dir / "response.json"),
            }
        except Exception as exc:
            last_error = exc
            save_json(
                provider_dir / f"{model_name}.error.json",
                {
                    "model": model_name,
                    "error": str(exc),
                },
            )

    raise ApiError(f"Gemini failed for all candidate models: {last_error}")


def run_qwen(prompt: str, api_key: str, output_dir: Path) -> dict:
    provider_dir = output_dir / "qwen"
    provider_dir.mkdir(parents=True, exist_ok=True)
    model_candidates = ["qwen-image-2.0-pro", "qwen-image-2.0"]
    last_error: Exception | None = None

    for model_name in model_candidates:
        try:
            response = http_json(
                method="POST",
                url=QWEN_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                payload={
                    "model": model_name,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"text": prompt}],
                            }
                        ]
                    },
                    "parameters": {
                        "size": "1024*1024",
                        "n": 1,
                        "prompt_extend": True,
                        "watermark": False,
                    },
                },
            )
            save_json(provider_dir / "response.json", response.payload)

            image_url = extract_qwen_image_url(response.payload)
            image_path = download_file(image_url, provider_dir, "result")
            return {
                "provider": "qwen",
                "key": mask_key(api_key),
                "model": model_name,
                "image_url": image_url,
                "image_path": str(image_path),
                "response_path": str(provider_dir / "response.json"),
            }
        except Exception as exc:
            last_error = exc
            save_json(
                provider_dir / f"{model_name}.error.json",
                {
                    "model": model_name,
                    "error": str(exc),
                },
            )

    raise ApiError(f"Qwen failed for all candidate models: {last_error}")


def extract_qwen_image_url(payload: dict) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ApiError(f"Qwen returned no output object: {json.dumps(payload, ensure_ascii=False)}")
    choices = output.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ApiError(f"Qwen returned no choices: {json.dumps(payload, ensure_ascii=False)}")
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                return str(item["image"])
    raise ApiError(f"Qwen returned no image url: {json.dumps(payload, ensure_ascii=False)}")


def extract_gemini_image(payload: dict) -> tuple[bytes, str]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ApiError(f"Gemini returned no candidates: {json.dumps(payload, ensure_ascii=False)}")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline_data, dict):
                continue
            encoded = inline_data.get("data")
            if not encoded:
                continue
            mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png")
            return decode_base64_string(str(encoded), "Gemini image data"), mime_type
    raise ApiError(f"Gemini returned no inline image data: {json.dumps(payload, ensure_ascii=False)}")


def decode_base64_string(data: str, label: str) -> bytes:
    try:
        import base64

        return base64.b64decode(data)
    except Exception as exc:
        raise ApiError(f"Failed to decode {label}: {exc}") from exc


def run_wuli(prompt: str, api_keys: list[str], output_dir: Path, poll_interval: float, timeout: float) -> dict:
    provider_dir = output_dir / "wuli"
    provider_dir.mkdir(parents=True, exist_ok=True)
    model_candidates = ["Qwen Image Turbo", "Qwen Image 2.0"]
    last_error: Exception | None = None

    for key_index, api_key in enumerate(api_keys, start=1):
        key_dir = provider_dir / f"key-{key_index}"
        key_dir.mkdir(parents=True, exist_ok=True)
        for model_name in model_candidates:
            try:
                result = run_wuli_once(
                    prompt=prompt,
                    api_key=api_key,
                    model_name=model_name,
                    output_dir=key_dir,
                    poll_interval=poll_interval,
                    timeout=timeout,
                )
                result["key"] = mask_key(api_key)
                return result
            except Exception as exc:
                last_error = exc
                save_json(
                    key_dir / f"{model_name}.error.json",
                    {
                        "model": model_name,
                        "error": str(exc),
                    },
                )

    raise ApiError(f"Wuli failed for all keys/models: {last_error}")


def run_wuli_once(
    *,
    prompt: str,
    api_key: str,
    model_name: str,
    output_dir: Path,
    poll_interval: float,
    timeout: float,
) -> dict:
    submit_response = http_json(
        method="POST",
        url=f"{WULI_BASE}/predict/submit",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={
            "modelName": model_name,
            "prompt": prompt,
            "mediaType": "IMAGE",
            "predictType": "TXT_2_IMG",
            "aspectRatio": "1:1",
            "resolution": "2K",
            "n": 1,
            "optimizePrompt": True,
        },
    )
    ensure_success_flag("Wuli submit", submit_response.payload)
    save_json(output_dir / "submit.json", submit_response.payload)

    record_id = (
        submit_response.payload.get("data", {}).get("recordId")
        if isinstance(submit_response.payload.get("data"), dict)
        else None
    )
    if not record_id:
        raise ApiError(f"Wuli submit returned no recordId: {submit_response.raw_text}")

    deadline = time.monotonic() + timeout
    last_query_payload: dict | None = None
    while time.monotonic() < deadline:
        encoded_record_id = urllib.parse.quote(str(record_id), safe="")
        query_response = http_json(
            method="GET",
            url=f"{WULI_BASE}/predict/query?recordId={encoded_record_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        ensure_success_flag("Wuli query", query_response.payload)
        last_query_payload = query_response.payload
        save_json(output_dir / "query-latest.json", query_response.payload)

        data = query_response.payload.get("data")
        if not isinstance(data, dict):
            raise ApiError(f"Wuli query returned invalid data: {query_response.raw_text}")
        status = str(data.get("recordStatus") or "")
        if status in WULI_TERMINAL_STATES:
            if status != "SUCCEED":
                raise ApiError(f"Wuli task ended with status={status}: {json.dumps(data, ensure_ascii=False)}")
            image_url = extract_wuli_image_url(data)
            image_path = download_file(image_url, output_dir, "result")
            return {
                "provider": "wuli",
                "model": model_name,
                "record_id": record_id,
                "image_url": image_url,
                "image_path": str(image_path),
                "submit_path": str(output_dir / "submit.json"),
                "query_path": str(output_dir / "query-latest.json"),
            }

        time.sleep(poll_interval)

    raise ApiError(
        f"Wuli polling timed out after {timeout}s. Last payload: "
        f"{json.dumps(last_query_payload or {}, ensure_ascii=False)}"
    )


def extract_wuli_image_url(data: dict) -> str:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        raise ApiError(f"Wuli returned no results: {json.dumps(data, ensure_ascii=False)}")
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "SUCCEED":
            continue
        image_url = item.get("imageUrl")
        if image_url:
            return str(image_url)
    raise ApiError(f"Wuli returned no successful image url: {json.dumps(data, ensure_ascii=False)}")


def main() -> int:
    args = parse_args()
    requested_providers = [normalize_provider_name(item) for item in args.providers.split(",") if item.strip()]
    output_dir = make_output_dir(args.output_dir)
    keys = load_keys(Path(args.keys_file).expanduser().resolve())
    summary: dict[str, dict] = {"output_dir": str(output_dir), "results": {}, "errors": {}}

    for provider in requested_providers:
        try:
            if provider == "openai":
                provider_settings = keys.get("openai")
                provider_keys = provider_settings.values if provider_settings else []
                if not provider_keys:
                    raise ApiError("No OpenAI key found in keys.txt")
                api_base_url = provider_settings.options.get("apibaseurl") if provider_settings else None
                result = run_openai(args.prompt, provider_keys[0], output_dir, api_base_url=api_base_url)
            elif provider == "gemini":
                provider_settings = keys.get("gemini")
                provider_keys = provider_settings.values if provider_settings else []
                if not provider_keys:
                    raise ApiError("No Gemini key found in keys.txt")
                gemini_models = [item.strip() for item in args.gemini_models.split(",") if item.strip()]
                result = run_gemini(args.prompt, provider_keys[0], output_dir, gemini_models)
            elif provider == "agens":
                provider_settings = keys.get("agens")
                provider_keys = provider_settings.values if provider_settings else []
                if not provider_keys:
                    raise ApiError("No Agens key found in keys.txt")
                result = run_agens(args.prompt, provider_keys[0], output_dir)
            elif provider == "qwen":
                provider_settings = keys.get("qwen")
                provider_keys = provider_settings.values if provider_settings else []
                if not provider_keys:
                    raise ApiError("No Qwen key found in keys.txt")
                result = run_qwen(args.prompt, provider_keys[0], output_dir)
            elif provider == "wuli":
                provider_settings = keys.get("wuli")
                provider_keys = provider_settings.values if provider_settings else []
                if not provider_keys:
                    raise ApiError("No Wuli key found in keys.txt")
                result = run_wuli(
                    args.prompt,
                    provider_keys,
                    output_dir,
                    poll_interval=args.wuli_poll_interval,
                    timeout=args.wuli_timeout,
                )
            else:
                raise ApiError(f"Unsupported provider '{provider}'")

            summary["results"][provider] = result
            print(f"[ok] {provider}: {result['image_path']}")
        except Exception as exc:
            summary["errors"][provider] = {"error": str(exc)}
            print(f"[error] {provider}: {exc}", file=sys.stderr)

    save_json(output_dir / "summary.json", summary)
    print(f"[summary] {output_dir / 'summary.json'}")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
