"""YAML-driven provider registry."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from voice_benchmarking_platform.providers.base import STTProvider
from voice_benchmarking_platform.providers.yaml_provider import YAMLProvider

_DEFAULT_YAML = Path(__file__).parents[3] / "providers.yaml"


def _load_raw(yaml_path: Path | None) -> list[dict]:
    path = yaml_path or _DEFAULT_YAML
    if not path.exists():
        return []
    with path.open() as f:
        return yaml.safe_load(f).get("providers", [])


def load_yaml_providers(yaml_path: Path | None = None) -> list[YAMLProvider]:
    """Return one YAMLProvider per entry (using the default model).

    Providers whose API key is missing are skipped.
    """
    providers: list[YAMLProvider] = []
    for cfg in _load_raw(yaml_path):
        key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            continue
        providers.append(YAMLProvider(config=cfg, api_key=key))
    return providers


def get_provider_by_name(
    name: str,
    api_key: str | None = None,
    yaml_path: Path | None = None,
) -> STTProvider | None:
    """Return a provider for ``name``, which may be ``provider`` or ``provider:model``.

    ``api_key`` overrides the environment variable when provided.
    """
    base_name, model = (name.split(":", 1) + [None])[:2]  # type: ignore[list-item]

    for cfg in _load_raw(yaml_path):
        if cfg["name"] != base_name:
            continue
        key = api_key or os.environ.get(cfg.get("api_key_env", ""), "")
        if not key:
            return None
        return YAMLProvider(config=cfg, api_key=key, model=model)
    return None


def list_available_providers(yaml_path: Path | None = None) -> list[dict]:
    """Return display metadata for every YAML-defined provider, including model lists.

    Returned regardless of whether the API key is set, so the UI can render
    all options and indicate which ones need configuration.
    """
    return [
        {
            "name": cfg["name"],
            "display_name": cfg.get("display_name", cfg["name"]),
            "api_key_env": cfg.get("api_key_env", ""),
            "default_model": cfg.get("model_version", ""),
            "available_models": cfg.get("available_models", []),
        }
        for cfg in _load_raw(yaml_path)
    ]
