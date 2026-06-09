from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config_models import AppConfig, KeyConfig, ModelConfig, build_default_config
from app.db.key_status import KeyStatusRepository


class UnknownModelError(LookupError):
    pass


class NoAvailableKeyError(RuntimeError):
    pass


_UNSET = object()


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._cache: AppConfig | None = None

    def ensure_exists(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.save(build_default_config())

    def read(self) -> AppConfig:
        with self._lock:
            return self._load().model_copy(deep=True)

    def save(self, config: AppConfig) -> None:
        with self._lock:
            self._write(config.model_copy(deep=True))

    def transaction(self, mutator):
        with self._lock:
            config = self._load()
            result = mutator(config)
            self._write(config)
            return result

    def _load(self) -> AppConfig:
        if self._cache is None:
            payload = self.path.read_text(encoding="utf-8")
            self._cache = AppConfig.model_validate_json(payload)
        return self._cache

    def _write(self, config: AppConfig) -> None:
        payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
        self.path.write_text(f"{payload}\n", encoding="utf-8")
        self._cache = config


class KeyManager:
    cooling_window = timedelta(days=2)

    def __init__(self, config_store: ConfigStore, key_status_repo: KeyStatusRepository) -> None:
        self.config_store = config_store
        self.key_status_repo = key_status_repo
        self._lock = threading.RLock()
        self._round_robin_positions: dict[str, int] = defaultdict(int)

    def sync_key_statuses(self) -> None:
        config = self.config_store.read()
        self.key_status_repo.replace_snapshot(self._snapshot_records(config))

    def count_available_keys(self, model_name: str, exclude: set[str] | None = None) -> int:
        config = self.config_store.read()
        model = config.models.get(model_name)
        if model is None:
            raise UnknownModelError(model_name)
        excluded = exclude or set()
        return sum(
            1
            for key in model.keys
            if self._is_selectable_candidate(key) and key.id not in excluded
        )

    def select_next_key(
        self,
        model_name: str,
        exclude: set[str] | None = None,
    ) -> tuple[ModelConfig, KeyConfig]:
        with self._lock:
            config = self.config_store.read()
            model = config.models.get(model_name)
            if model is None:
                raise UnknownModelError(model_name)

            excluded = exclude or set()
            candidates = [key for key in model.keys if self._is_selectable_candidate(key) and key.id not in excluded]
            if not candidates:
                raise NoAvailableKeyError(f"No active or retry-ready keys available for model '{model_name}'")

            index = self._round_robin_positions[model_name] % len(candidates)
            chosen = candidates[index]
            self._round_robin_positions[model_name] = (index + 1) % len(candidates)
            used_at = datetime.now(UTC)

            def update_last_used(config_to_update: AppConfig) -> None:
                key = self._find_key(config_to_update, model_name, chosen.id)
                key.last_used = used_at

            self.config_store.transaction(update_last_used)
            chosen.last_used = used_at
            return model, chosen

    def record_success(
        self,
        model_name: str,
        key_id: str,
        *,
        quota_remaining_percent: int | None | object = _UNSET,
    ) -> None:
        with self._lock:
            succeeded_at = datetime.now(UTC)

            def mutate(config: AppConfig) -> None:
                key = self._find_key(config, model_name, key_id)
                key.status = "active"
                key.cooling_until = None
                key.consecutive_failures = 0
                key.last_success_at = succeeded_at
                key.last_used = succeeded_at
                key.last_error = None
                if quota_remaining_percent is not _UNSET:
                    key.quota_remaining_percent = quota_remaining_percent
                elif key.quota_remaining_percent == 0:
                    key.quota_remaining_percent = None

            self.config_store.transaction(mutate)
            self.sync_key_statuses()

    def record_failure(self, model_name: str, key_id: str, kind: str, message: str) -> None:
        with self._lock:
            failed_at = datetime.now(UTC)

            def mutate(config: AppConfig) -> None:
                key = self._find_key(config, model_name, key_id)
                key.last_error = message[:500]
                key.last_used = failed_at
                if kind not in {"quota_exceeded", "rate_limit"}:
                    return
                if kind == "quota_exceeded":
                    key.quota_remaining_percent = 0
                key.consecutive_failures += 1
                if key.consecutive_failures >= 3:
                    key.status = "invalid"
                    key.cooling_until = None
                else:
                    key.status = "cooling"
                    key.cooling_until = failed_at + self.cooling_window

            self.config_store.transaction(mutate)
            self.sync_key_statuses()

    def get_models_overview(self) -> dict:
        config = self.config_store.read()
        models = []
        for model_name, model in config.models.items():
            active_keys = [key for key in model.keys if key.status == "active"]
            retry_ready_keys = [key for key in model.keys if self._is_retry_ready(key)]
            next_key_id = None
            current_key = None
            selectable_candidates = [key for key in model.keys if self._is_selectable_candidate(key)]
            if selectable_candidates:
                selected_key = selectable_candidates[
                    self._round_robin_positions[model_name] % len(selectable_candidates)
                ]
                next_key_id = selected_key.id
                current_key = self._key_payload(selected_key)
            models.append(
                {
                    "id": model_name,
                    "display_name": model.display_name,
                    "provider": model.provider,
                    "api_base": model.api_base,
                    "model_name": model.model_name,
                    "active_key_count": len(active_keys),
                    "retry_ready_key_count": len(retry_ready_keys),
                    "total_key_count": len(model.keys),
                    "next_key_id": next_key_id,
                    "current_key": current_key,
                    "keys": [self._key_payload(key) for key in model.keys],
                }
            )
        return {"default_model": config.default_model, "models": models}

    def get_health_snapshot(self) -> dict:
        config = self.config_store.read()
        models = []
        totals = {"active": 0, "cooling": 0, "invalid": 0}
        for model_name, model in config.models.items():
            counts = {"active": 0, "cooling": 0, "invalid": 0}
            for key in model.keys:
                counts[key.status] += 1
                totals[key.status] += 1
            models.append(
                {
                    "id": model_name,
                    "display_name": model.display_name,
                    "counts": counts,
                    "retry_ready_count": sum(1 for key in model.keys if self._is_retry_ready(key)),
                    "keys": [self._key_payload(key) for key in model.keys],
                }
            )
        return {"totals": totals, "models": models}

    def _find_key(self, config: AppConfig, model_name: str, key_id: str) -> KeyConfig:
        model = config.models.get(model_name)
        if model is None:
            raise UnknownModelError(model_name)
        for key in model.keys:
            if key.id == key_id:
                return key
        raise NoAvailableKeyError(f"Unknown key '{key_id}' for model '{model_name}'")

    def _key_payload(self, key: KeyConfig) -> dict:
        return {
            "id": key.id,
            "status": key.status,
            "retry_ready": self._is_retry_ready(key),
            "cooling_until": key.cooling_until.isoformat() if key.cooling_until else None,
            "consecutive_failures": key.consecutive_failures,
            "last_used": key.last_used.isoformat() if key.last_used else None,
            "last_success_at": key.last_success_at.isoformat() if key.last_success_at else None,
            "quota_remaining_percent": key.quota_remaining_percent,
            "last_error": key.last_error,
        }

    def _is_retry_ready(self, key: KeyConfig) -> bool:
        return bool(key.status == "cooling" and key.cooling_until and key.cooling_until <= datetime.now(UTC))

    def _is_selectable_candidate(self, key: KeyConfig) -> bool:
        return key.status == "active" or self._is_retry_ready(key)

    def _snapshot_records(self, config: AppConfig) -> list[dict]:
        updated_at = datetime.now().isoformat(timespec="seconds")
        records = []
        for model_name, model in config.models.items():
            for key in model.keys:
                records.append(
                    {
                        "key_id": key.id,
                        "model": model_name,
                        "status": key.status,
                        "consecutive_failures": key.consecutive_failures,
                        "cooling_until": key.cooling_until.isoformat() if key.cooling_until else None,
                        "last_success_at": key.last_success_at.isoformat() if key.last_success_at else None,
                        "last_used": key.last_used.isoformat() if key.last_used else None,
                        "quota_remaining_percent": key.quota_remaining_percent,
                        "last_error": key.last_error,
                        "updated_at": updated_at,
                    }
                )
        return records
