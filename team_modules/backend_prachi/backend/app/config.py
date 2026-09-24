"""Load/save station + physical-limit configuration from disk.

The Admin System reads and writes this file, so config.py also supports
reloading and saving so admin edits are picked up by the rest of the app.
"""
import json
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_BASE, "config", "station.json")

_config = None


def get_config() -> dict:
    """Return the loaded config, with a clear error if the file is missing."""
    global _config
    if _config is None:
        reload_config()
    return _config


def reload_config() -> dict:
    """Re-read the config file from disk. Use after an admin edit."""
    global _config
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Station config not found at: {CONFIG_PATH}. "
            f"Create backend/config/station.json first."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config = json.load(f)
    return _config


def save_config() -> None:
    """Persist the in-memory config back to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_config, f, indent=2, ensure_ascii=False)


def get_physical_limits() -> dict:
    return get_config()["physical_limits"]


def get_resource_config() -> dict:
    """Return the resource catalog as a flat dict: id -> resource (for lookups)."""
    catalog = get_config().get("resource_catalog", {})
    flat = {}
    for group in catalog.values():
        for res in group:
            flat[res["id"]] = res
    return flat


def get_ai_models() -> dict:
    return get_config().get("ai_models", {})


def resource_groups() -> dict:
    """Return the resource catalog grouped by category."""
    return get_config().get("resource_catalog", {})