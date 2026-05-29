"""YAML-driven provider registry.

Load providers.yaml and instantiate YAMLProvider objects for each entry.
Python-coded providers (e.g. AssemblyAI) are returned via get_python_providers().
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from voice_benchmarking_platform.providers.base import STTProvider
from voice_benchmarking_platform.providers.yaml_provider import YAMLProvider

_DEFAULT_YAML = Path(__file__).parents[3] / "providers.yaml"


def load_yaml_providers(yaml_path: Path | None = None) -> list[YAMLProvider]:
    """Parse providers.yaml and return a list of YAMLProvider instances.

    API keys are read from environment variables named by each entry's
    ``api_key_env`` field. Providers whose key is missing are skipped.
    """
    path = yaml_path or _DEFAULT_YAML
    if not path.exists():
        return []

    with path.open() as f:
        data = yaml.safe_load(f)

    providers: list[YAMLProvider] = []
    for cfg in data.get("providers", []):
        key_env = cfg.get("api_key_env", "")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            continue
        providers.append(YAMLProvider(config=cfg, api_key=api_key))
    return providers


def get_provider_by_name(
    name: str,
    api_key: str | None = None,
    yaml_path: Path | None = None,
) -> STTProvider | None:
    """Return the provider matching ``name``, or None if not found.

    ``api_key`` overrides the environment variable when provided.
    """
    path = yaml_path or _DEFAULT_YAML
    if not path.exists():
        return None

    with path.open() as f:
        data = yaml.safe_load(f)

    for cfg in data.get("providers", []):
        if cfg["name"] != name:
            continue
        key_env = cfg.get("api_key_env", "")
        key = api_key or os.environ.get(key_env, "")
        if not key:
            return None
        return YAMLProvider(config=cfg, api_key=key)
    return None


def list_available_providers(yaml_path: Path | None = None) -> list[dict]:
    """Return metadata (name, display_name, api_key_env) for every YAML-defined provider.

    Entries are returned regardless of whether the API key is set, so the UI
    can render them all and signal which ones need configuration.
    """
    path = yaml_path or _DEFAULT_YAML
    if not path.exists():
        return []

    with path.open() as f:
        data = yaml.safe_load(f)

    return [
        {
            "name": cfg["name"],
            "display_name": cfg.get("display_name", cfg["name"]),
            "api_key_env": cfg.get("api_key_env", ""),
        }
        for cfg in data.get("providers", [])
    ]
