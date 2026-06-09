from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.application import create_app
from app.application import resolve_config_path
from app.config_models import KeyConfig, ModelConfig
from app.db.history import HistoryRepository
from app.db.key_status import KeyStatusRepository
from app.db.sqlite_db import Database
from app.services.generator import (
    GeminiNativeProvider,
    OpenAICompatibleProvider,
    ProviderArtifact,
    ProviderGenerationResult,
    ProviderQuotaError,
    ProviderRateLimitError,
    QwenNativeProvider,
    WuliNativeProvider,
    ImageGenerator,
    nearest_gemini_aspect_ratio,
    nearest_gemini_image_size,
)
from app.services.key_manager import ConfigStore, KeyManager
from app.services.translator import TranslationService


API_HEADERS = {"X-API-Key": "change-me"}


def create_test_app(tmp_path: Path):
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "imagegen.db"
    output_dir = tmp_path / "outputs"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<html><body>ui</body></html>", encoding="utf-8")
    return create_app(
        config_path=str(config_path),
        db_path=str(db_path),
        output_dir=str(output_dir),
        frontend_dir=str(frontend_dir),
    )


def test_resolve_config_path_prefers_explicit_env_local_default(tmp_path: Path, monkeypatch) -> None:
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    default_config = backend_dir / "config.json"
    local_config = backend_dir / "config.local.json"
    explicit_config = tmp_path / "explicit.json"
    env_config = tmp_path / "env.json"
    default_config.write_text("{}", encoding="utf-8")
    local_config.write_text("{}", encoding="utf-8")
    explicit_config.write_text("{}", encoding="utf-8")
    env_config.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("IMAGEGEN_CONFIG_PATH", str(env_config))
    assert resolve_config_path(str(explicit_config), backend_dir=backend_dir) == explicit_config
    assert resolve_config_path(None, backend_dir=backend_dir) == env_config

    monkeypatch.delenv("IMAGEGEN_CONFIG_PATH")
    assert resolve_config_path(None, backend_dir=backend_dir) == local_config

    local_config.unlink()
    assert resolve_config_path(None, backend_dir=backend_dir) == default_config


def test_generate_and_history_flow(tmp_path: Path) -> None:
    async def run_flow() -> None:
        app = create_test_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/api/models", headers=API_HEADERS)
                assert response.status_code == 200
                payload = response.json()
                assert payload["default_model"] == "agens"
                assert payload["models"][0]["keys"]
                assert payload["models"][0]["current_key"]["id"] == payload["models"][0]["next_key_id"]

                stats_response = await client.get("/api/stats", headers=API_HEADERS)
                assert stats_response.status_code == 200
                stats_payload = stats_response.json()
                assert stats_payload["current_key"]["id"] == stats_payload["current_key_id"]

                generate_response = await client.post(
                    "/api/images/generate",
                    headers=API_HEADERS,
                    json={
                        "model": "agens",
                        "prompt": "白色 GPS 追踪器，白底产品图",
                        "n": 2,
                        "size": "768x768",
                        "auto_translate": False,
                    },
                )
                assert generate_response.status_code == 200
                generate_payload = generate_response.json()
                assert generate_payload["model"] == "agens"
                assert len(generate_payload["data"]) == 2
                assert generate_payload["key_id"] in {"agens-01", "agens-02"}
                assert generate_payload["data"][0]["url"].startswith("http://testserver/static/outputs/")

                history_response = await client.get("/api/history", headers=API_HEADERS)
                assert history_response.status_code == 200
                history_payload = history_response.json()
                assert len(history_payload["items"]) == 1
                assert history_payload["items"][0]["prompt"] == "白色 GPS 追踪器，白底产品图"
                assert history_payload["items"][0]["thumbnail"].startswith("http://testserver/static/outputs/")
                assert history_payload["items"][0]["n"] == 2
                history_id = history_payload["items"][0]["id"]

                templates_response = await client.get("/api/templates", headers=API_HEADERS)
                assert templates_response.status_code == 200
                templates = templates_response.json()["items"]
                assert any(item["variables"] == ["product_name"] for item in templates)

                create_template_response = await client.post(
                    "/api/templates",
                    headers=API_HEADERS,
                    json={
                        "name": "带预览图模板",
                        "description": "包含预览图字段",
                        "template": "Poster for {product_name}",
                        "category": "海报图",
                        "preview_image_path": "/static/previews/template-1.png",
                    },
                )
                assert create_template_response.status_code == 201
                new_template_id = create_template_response.json()["id"]

                update_template_response = await client.put(
                    f"/api/templates/{new_template_id}",
                    headers=API_HEADERS,
                    json={
                        "name": "带预览图模板",
                        "description": "更新后的预览图字段",
                        "template": "Poster for {product_name}",
                        "category": "海报图",
                        "preview_image_path": "/static/previews/template-2.png",
                    },
                )
                assert update_template_response.status_code == 200

                templates_response = await client.get("/api/templates", headers=API_HEADERS)
                assert templates_response.status_code == 200
                created_template = next(
                    item for item in templates_response.json()["items"] if item["id"] == new_template_id
                )
                assert created_template["preview_image_path"] == "/static/previews/template-2.png"
                assert created_template["variables"] == ["product_name"]

                regenerate_response = await client.post(
                    f"/api/history/{history_id}/regenerate",
                    headers=API_HEADERS,
                    json={"model": "agens", "auto_translate": False},
                )
                assert regenerate_response.status_code == 200
                regenerate_payload = regenerate_response.json()
                assert len(regenerate_payload["data"]) == 2

                delete_response = await client.delete(f"/api/history/{history_id}", headers=API_HEADERS)
                assert delete_response.status_code == 200

                openai_response = await client.post(
                    "/v1/images/generations",
                    headers={"Authorization": "Bearer change-me"},
                    json={"model": "agens", "prompt": "product image", "n": 1, "size": "512x512"},
                )
                assert openai_response.status_code == 200
                assert len(openai_response.json()["data"]) == 1

                openai_b64_response = await client.post(
                    "/v1/images/generations",
                    headers={"Authorization": "Bearer change-me"},
                    json={
                        "model": "agens",
                        "prompt": "product image b64",
                        "n": 1,
                        "size": "512x512",
                        "response_format": "b64_json",
                    },
                )
                assert openai_b64_response.status_code == 200
                b64_payload = openai_b64_response.json()
                assert len(b64_payload["data"]) == 1
                assert "b64_json" in b64_payload["data"][0]
                assert base64.b64decode(b64_payload["data"][0]["b64_json"])

                unauthorized_response = await client.get("/api/models")
                assert unauthorized_response.status_code == 401

    asyncio.run(run_flow())


def test_key_cooling_and_reactivation(tmp_path: Path) -> None:
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.ensure_exists()
    repo = KeyStatusRepository(Database(tmp_path / "status.db"))
    repo.db.initialize()
    manager = KeyManager(config_store, repo)
    manager.sync_key_statuses()

    manager.record_failure("agens", "agens-01", "rate_limit", "too many requests")
    snapshot = manager.get_health_snapshot()
    first_key = next(model for model in snapshot["models"] if model["id"] == "agens")["keys"][0]
    assert first_key["status"] == "cooling"
    assert first_key["retry_ready"] is False

    def expire_cooling(config):
        config.models["agens"].keys[0].cooling_until = datetime.now(UTC) - timedelta(minutes=1)

    config_store.transaction(expire_cooling)
    refreshed = manager.get_models_overview()
    model = next(model for model in refreshed["models"] if model["id"] == "agens")
    key = model["keys"][0]
    assert key["status"] == "cooling"
    assert key["retry_ready"] is True
    assert model["current_key"]["id"] == "agens-01"

    selected_model, selected_key = manager.select_next_key("agens")
    assert selected_model.display_name == "Agens Image"
    assert selected_key.id == "agens-01"
    manager.record_success("agens", "agens-01")

    activated = manager.get_models_overview()
    key = next(model for model in activated["models"] if model["id"] == "agens")["keys"][0]
    assert key["status"] == "active"
    assert key["retry_ready"] is False


def test_quota_failure_updates_remaining_quota_state(tmp_path: Path) -> None:
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.ensure_exists()
    repo = KeyStatusRepository(Database(tmp_path / "status.db"))
    repo.db.initialize()
    manager = KeyManager(config_store, repo)
    manager.sync_key_statuses()

    manager.record_failure("agens", "agens-01", "quota_exceeded", "daily quota exceeded")
    cooled = next(model for model in manager.get_models_overview()["models"] if model["id"] == "agens")
    first_key = cooled["keys"][0]
    assert first_key["status"] == "cooling"
    assert first_key["quota_remaining_percent"] == 0

    manager.record_success("agens", "agens-01")
    recovered = next(model for model in manager.get_models_overview()["models"] if model["id"] == "agens")
    first_key = recovered["keys"][0]
    assert first_key["status"] == "active"
    assert first_key["quota_remaining_percent"] is None


def test_three_consecutive_failures_mark_key_invalid(tmp_path: Path) -> None:
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.ensure_exists()
    repo = KeyStatusRepository(Database(tmp_path / "status.db"))
    repo.db.initialize()
    manager = KeyManager(config_store, repo)
    manager.sync_key_statuses()

    manager.record_failure("agens", "agens-01", "rate_limit", "too many requests")
    manager.record_failure("agens", "agens-01", "rate_limit", "too many requests")
    manager.record_failure("agens", "agens-01", "rate_limit", "too many requests")

    snapshot = manager.get_health_snapshot()
    agens_model = next(model for model in snapshot["models"] if model["id"] == "agens")
    first_key = agens_model["keys"][0]
    assert first_key["status"] == "invalid"
    assert first_key["retry_ready"] is False
    assert first_key["consecutive_failures"] == 3
    assert first_key["cooling_until"] is None


def test_generator_failover_switches_to_next_key(tmp_path: Path) -> None:
    class StubTranslator:
        async def translate(self, prompt: str, enabled: bool = True) -> str:
            return prompt

    class FailoverProvider:
        async def generate(self, *, key_config: KeyConfig, count: int, **_: object) -> ProviderGenerationResult:
            if key_config.id == "agens-01":
                raise ProviderRateLimitError("rate limited")
            return ProviderGenerationResult(
                artifacts=[
                    ProviderArtifact(
                        content=b"fake-image",
                        extension="png",
                        mime_type="image/png",
                    )
                    for _ in range(count)
                ],
                quota_remaining_percent=37,
            )

    config_store = ConfigStore(tmp_path / "config.json")
    config_store.ensure_exists()
    db = Database(tmp_path / "imagegen.db")
    db.initialize()
    history_repo = HistoryRepository(db)
    repo = KeyStatusRepository(db)
    manager = KeyManager(config_store, repo)
    manager.sync_key_statuses()

    generator = ImageGenerator(
        key_manager=manager,
        history_repo=history_repo,
        translator=StubTranslator(),
        output_dir=tmp_path / "outputs",
    )
    generator.providers["mock"] = FailoverProvider()

    async def run_case() -> dict:
        try:
            return await generator.generate(
                model_name="agens",
                prompt="test prompt",
                count=1,
                size="512x512",
                public_base_url="http://testserver",
                auto_translate=False,
            )
        finally:
            await generator.aclose()

    payload = asyncio.run(run_case())

    assert payload["key_id"] == "agens-02"
    snapshot = manager.get_health_snapshot()
    agens_model = next(model for model in snapshot["models"] if model["id"] == "agens")
    assert agens_model["keys"][0]["status"] == "cooling"
    assert agens_model["keys"][1]["status"] == "active"
    assert agens_model["keys"][1]["quota_remaining_percent"] == 37

    history = history_repo.list_recent()
    assert len(history) == 1
    assert history[0]["key_id"] == "agens-02"


def test_translation_service_falls_back_to_original_prompt_on_error(tmp_path: Path) -> None:
    class FailingClient:
        async def post(self, url: str, **_: object) -> httpx.Response:
            request = httpx.Request("POST", url)
            return httpx.Response(500, request=request, json={"error": {"message": "translator failed"}})

        async def aclose(self) -> None:
            return None

    config_store = ConfigStore(tmp_path / "config.json")
    config_store.ensure_exists()

    def configure_translation(config) -> None:
        config.translation.enabled = True
        config.translation.provider = "openai_compatible"
        config.translation.api_base = "https://translator.example/v1"
        config.translation.api_key = "sk-test"
        config.translation.model = "gpt-test"

    config_store.transaction(configure_translation)
    service = TranslationService(config_store)
    service.client = FailingClient()

    async def run_case() -> str:
        try:
            return await service.translate("白色产品图", enabled=True)
        finally:
            await service.aclose()

    result = asyncio.run(run_case())
    assert result == "白色产品图"


def test_generate_with_template_variables_and_delete_history_removes_file(tmp_path: Path) -> None:
    async def run_flow() -> None:
        app = create_test_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_template_response = await client.post(
                    "/api/templates",
                    headers=API_HEADERS,
                    json={
                        "name": "变量模板",
                        "description": "用于变量替换测试",
                        "template": "Poster for {product_name} in {scene_name}",
                        "category": "海报图",
                        "preview_image_path": "",
                    },
                )
                assert create_template_response.status_code == 201
                template_id = create_template_response.json()["id"]

                generate_response = await client.post(
                    "/api/images/generate",
                    headers=API_HEADERS,
                    json={
                        "model": "agens",
                        "prompt": "",
                        "template_id": template_id,
                        "variables": {
                            "product_name": "D606 GPS tracker",
                            "scene_name": "a clean studio setup",
                        },
                        "n": 1,
                        "size": "768x768",
                        "auto_translate": False,
                    },
                )
                assert generate_response.status_code == 200
                generate_payload = generate_response.json()
                assert len(generate_payload["data"]) == 1

                history_response = await client.get("/api/history", headers=API_HEADERS)
                assert history_response.status_code == 200
                history_item = history_response.json()["items"][0]
                assert history_item["prompt"] == "Poster for D606 GPS tracker in a clean studio setup"

                image_path = Path(generate_payload["data"][0]["path"])
                assert image_path.exists()

                delete_response = await client.delete(f"/api/history/{history_item['id']}", headers=API_HEADERS)
                assert delete_response.status_code == 200
                assert not image_path.exists()

    asyncio.run(run_flow())


def test_openai_compatible_provider_supports_multiple_auth_modes() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(b"fake-image").decode("ascii")}]},
        )

    transport = httpx.MockTransport(handler)

    async def run_cases() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(client)
            bearer_model = ModelConfig(
                display_name="Bearer",
                provider="openai_compatible",
                api_base="https://example.com/v1",
                model_name="bearer-model",
                provider_options={"auth_mode": "bearer"},
            )
            header_model = ModelConfig(
                display_name="Header",
                provider="openai_compatible",
                api_base="https://example.com/v1",
                model_name="header-model",
                provider_options={
                    "auth_mode": "header",
                    "auth_header": "X-API-Key",
                    "request_body": {"style": "studio"},
                },
            )
            query_model = ModelConfig(
                display_name="Query",
                provider="openai_compatible",
                api_base="https://example.com/v1",
                model_name="query-model",
                provider_options={
                    "auth_mode": "query",
                    "api_key_query_name": "key",
                    "omit_model": True,
                },
            )

            bearer_result = await provider.generate(
                alias="bearer",
                model_config=bearer_model,
                key_config=KeyConfig(id="key-1", key="secret-1"),
                prompt="prompt one",
                count=1,
                size="1024x1024",
            )
            header_result = await provider.generate(
                alias="header",
                model_config=header_model,
                key_config=KeyConfig(id="key-2", key="secret-2"),
                prompt="prompt two",
                count=2,
                size="768x768",
            )
            query_result = await provider.generate(
                alias="query",
                model_config=query_model,
                key_config=KeyConfig(id="key-3", key="secret-3"),
                prompt="prompt three",
                count=1,
                size="512x512",
            )
            assert len(bearer_result.artifacts) == 1
            assert len(header_result.artifacts) == 1
            assert len(query_result.artifacts) == 1

    asyncio.run(run_cases())

    assert len(captured_requests) == 3
    assert captured_requests[0].headers["Authorization"] == "Bearer secret-1"
    assert json.loads(captured_requests[0].content)["model"] == "bearer-model"

    assert captured_requests[1].headers["X-API-Key"] == "secret-2"
    header_payload = json.loads(captured_requests[1].content)
    assert header_payload["style"] == "studio"
    assert header_payload["n"] == 2

    assert "key=secret-3" in str(captured_requests[2].url)
    query_payload = json.loads(captured_requests[2].content)
    assert "model" not in query_payload
    assert query_payload["prompt"] == "prompt three"


def test_gemini_native_provider_builds_request_and_parses_inline_image() -> None:
    captured_request: dict[str, object] = {}
    encoded_image = base64.b64encode(b"png-bytes").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": encoded_image,
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_case() -> list:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GeminiNativeProvider(client)
            return await provider.generate(
                alias="gemini",
                model_config=ModelConfig(
                    display_name="Gemini",
                    provider="gemini_native",
                    api_base="https://generativelanguage.googleapis.com/v1beta",
                    model_name="gemini-2.5-flash-image",
                    provider_options={"response_modalities": ["IMAGE"]},
                ),
                key_config=KeyConfig(id="gemini-01", key="AIza-test"),
                prompt="Create a premium product image",
                count=1,
                size="1536x1024",
            )

    artifacts = asyncio.run(run_case())

    assert len(artifacts.artifacts) == 1
    assert artifacts.artifacts[0].content == b"png-bytes"
    assert artifacts.artifacts[0].mime_type == "image/png"
    assert captured_request["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    request_headers = captured_request["headers"]
    assert request_headers["x-goog-api-key"] == "AIza-test"
    request_json = captured_request["json"]
    assert request_json["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert request_json["generationConfig"]["imageConfig"]["aspectRatio"] == "3:2"
    assert request_json["generationConfig"]["imageConfig"]["imageSize"] == "2K"


def test_gemini_native_provider_supports_multiple_images_via_sequential_requests() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        image_bytes = f"image-{len(captured_urls)}".encode("utf-8")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_case() -> ProviderGenerationResult:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GeminiNativeProvider(client)
            return await provider.generate(
                alias="gemini",
                model_config=ModelConfig(
                    display_name="Gemini",
                    provider="gemini_native",
                    api_base="https://generativelanguage.googleapis.com/v1beta",
                    model_name="gemini-2.5-flash-image",
                ),
                key_config=KeyConfig(id="gemini-01", key="AIza-test"),
                prompt="Create a premium product image",
                count=3,
                size="1024x1024",
            )

    result = asyncio.run(run_case())
    assert len(result.artifacts) == 3
    assert [item.content for item in result.artifacts] == [b"image-1", b"image-2", b"image-3"]
    assert len(captured_urls) == 3


def test_qwen_native_provider_builds_request_and_downloads_images() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured_request["url"] = str(request.url)
            captured_request["headers"] = dict(request.headers)
            captured_request["json"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [
                                        {"image": "https://cdn.example.com/generated-1.png"},
                                        {"image": "https://cdn.example.com/generated-2.png"},
                                    ]
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)

    async def run_case() -> ProviderGenerationResult:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = QwenNativeProvider(client)
            return await provider.generate(
                alias="qwen",
                model_config=ModelConfig(
                    display_name="Qwen",
                    provider="qwen_native",
                    api_base="https://dashscope.aliyuncs.com/api/v1",
                    model_name="qwen-image",
                    provider_options={"parameters": {"seed": 42}},
                ),
                key_config=KeyConfig(id="qwen-01", key="sk-qwen"),
                prompt="A premium product photo on white background",
                count=2,
                size="1024x768",
            )

    result = asyncio.run(run_case())
    assert len(result.artifacts) == 2
    assert [item.content for item in result.artifacts] == [b"png-bytes", b"png-bytes"]
    assert captured_request["url"] == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    request_headers = {str(key).lower(): value for key, value in dict(captured_request["headers"]).items()}
    assert request_headers["authorization"] == "Bearer sk-qwen"
    request_json = captured_request["json"]
    assert request_json["model"] == "qwen-image"
    assert request_json["input"]["messages"][0]["content"][0]["text"] == "A premium product photo on white background"
    assert request_json["parameters"]["n"] == 2
    assert request_json["parameters"]["size"] == "1024*768"
    assert request_json["parameters"]["prompt_extend"] is True
    assert request_json["parameters"]["watermark"] is False
    assert request_json["parameters"]["seed"] == 42


def test_wuli_native_provider_submits_and_polls_images() -> None:
    captured_requests: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = None
        if request.content:
            payload = json.loads(request.content)
        captured_requests.append((request.method, str(request.url), payload))
        if request.method == "POST" and request.url.path.endswith("/predict/submit"):
            return httpx.Response(200, json={"success": True, "data": {"recordId": "rec-123"}})
        if request.method == "GET" and request.url.path.endswith("/predict/query"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "recordStatus": "SUCCEED",
                        "results": [
                            {
                                "status": "SUCCEED",
                                "imageUrl": "https://cdn.example.com/generated.jpeg",
                            }
                        ],
                    },
                },
            )
        return httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})

    transport = httpx.MockTransport(handler)

    async def run_case() -> ProviderGenerationResult:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = WuliNativeProvider(client)
            provider._sleep = _noop_sleep  # type: ignore[method-assign]
            return await provider.generate(
                alias="wuli",
                model_config=ModelConfig(
                    display_name="Wuli",
                    provider="wuli_native",
                    api_base="https://platform.wuli.art/api/v1/platform",
                    model_name="Qwen Image Turbo",
                    provider_options={"poll_interval_seconds": 0.01, "poll_timeout_seconds": 1},
                ),
                key_config=KeyConfig(id="wuli-01", key="wuli-secret"),
                prompt="A premium product photo on white background",
                count=1,
                size="1024x768",
            )

    result = asyncio.run(run_case())
    assert len(result.artifacts) == 1
    assert result.artifacts[0].content == b"jpeg-bytes"
    assert result.artifacts[0].mime_type == "image/jpeg"

    submit_method, submit_url, submit_payload = captured_requests[0]
    assert submit_method == "POST"
    assert submit_url == "https://platform.wuli.art/api/v1/platform/predict/submit"
    assert submit_payload["modelName"] == "Qwen Image Turbo"
    assert submit_payload["predictType"] == "TXT_2_IMG"
    assert submit_payload["aspectRatio"] == "4:3"
    assert submit_payload["resolution"] == "1K"

    query_method, query_url, _ = captured_requests[1]
    assert query_method == "GET"
    assert "recordId=rec-123" in query_url


async def _noop_sleep(_: float) -> None:
    return None


def test_openai_compatible_provider_extracts_quota_remaining_percent() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                200,
                headers={"X-Quota-Remaining-Percent": "42"},
                json={"data": [{"b64_json": base64.b64encode(b"image-one").decode("ascii")}]},
            )
        return httpx.Response(
            200,
            json={
                "data": [{"b64_json": base64.b64encode(b"image-two").decode("ascii")}],
                "meta": {"quota": {"remaining": 0.58}},
            },
        )

    transport = httpx.MockTransport(handler)

    async def run_cases() -> tuple[ProviderGenerationResult, ProviderGenerationResult]:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(client)
            header_result = await provider.generate(
                alias="header-quota",
                model_config=ModelConfig(
                    display_name="HeaderQuota",
                    provider="openai_compatible",
                    api_base="https://example.com/v1",
                    model_name="header-quota-model",
                    provider_options={
                        "quota_remaining_percent_header": "X-Quota-Remaining-Percent",
                    },
                ),
                key_config=KeyConfig(id="key-1", key="secret-1"),
                prompt="prompt one",
                count=1,
                size="1024x1024",
            )
            json_result = await provider.generate(
                alias="json-quota",
                model_config=ModelConfig(
                    display_name="JsonQuota",
                    provider="openai_compatible",
                    api_base="https://example.com/v1",
                    model_name="json-quota-model",
                    provider_options={
                        "quota_remaining_percent_json_path": "meta.quota.remaining",
                        "quota_remaining_percent_multiplier": 100,
                    },
                ),
                key_config=KeyConfig(id="key-2", key="secret-2"),
                prompt="prompt two",
                count=1,
                size="1024x1024",
            )
            return header_result, json_result

    header_result, json_result = asyncio.run(run_cases())
    assert header_result.quota_remaining_percent == 42
    assert json_result.quota_remaining_percent == 58


def test_provider_error_classification_and_gemini_helpers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota exceeded for today"}})

    transport = httpx.MockTransport(handler)

    async def run_case() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(client)
            await provider.generate(
                alias="agens",
                model_config=ModelConfig(
                    display_name="Agens",
                    provider="openai_compatible",
                    api_base="https://example.com/v1",
                    model_name="agens-image",
                ),
                key_config=KeyConfig(id="agens-01", key="secret"),
                prompt="test",
                count=1,
                size="1024x1024",
            )

    try:
        asyncio.run(run_case())
    except ProviderQuotaError as error:
        assert "quota exceeded" in str(error)
    else:
        raise AssertionError("Expected ProviderQuotaError")

    assert nearest_gemini_aspect_ratio(1500, 1000) == "3:2"
    assert nearest_gemini_aspect_ratio(1024, 1024) == "1:1"
    assert nearest_gemini_image_size(1536, 1024) == "2K"
    assert nearest_gemini_image_size(700, 700) == "0.5K"
