"""Admin System: the administrator defines/changes station + resource configuration.

This is the human-in-the-loop layer. Sensors feed data (Prachi), the AI predicts
(Aashika), the optimizer decides (Bhoomi) — and the ADMIN decides what resources
exist, their capacity, and whether each one is ONLINE/OFFLINE.

Changes are validated against the physical limits and persisted to
config/station.json so they survive restarts.
"""
from ..config import get_config, save_config, reload_config, get_resource_config

VALID_STATUS = {
    "ONLINE", "OFFLINE", "AVAILABLE", "UNAVAILABLE", "ACTIVE", "INACTIVE", "RUNNING",
    "CHARGING", "DISCHARGING", "IDLE", "STANDBY", "READY", "GENERATING"
}
VALID_FIELDS = {
    "enabled", "status", "capacity_kw", "capacity_kwh", "soc_percent",
    "online", "output_kw", "condition", "maintenance", "battery_soc",
    "battery_enabled", "battery_state"
}
# Map frontend UI resource IDs to catalog IDs
RESOURCE_ALIASES = {
    "solar": "solar_pv",
    "hydro": "hydropower",
    "generator": "backup_generator",
    "passive": "passive_solar",
    "solarthermal": "solar_thermal",
    "solar-thermal": "solar_thermal",
}
# These must stay inside the physical limits defined in config/station.json.
LIMITED_FIELDS = {"soc_percent": "battery_soc_pct",
                  "capacity_kw": "solar_generation_kw",
                  "capacity_kwh": None}


class AdminError(Exception):
    """Raised when the admin asks for something invalid."""


def _check_physical_limit(field: str, value) -> None:
    """Reject out-of-range values using the physical limits (0 for negatives)."""
    limits = get_config().get("physical_limits", {})
    if field == "soc_percent":
        lo, hi = limits.get("battery_soc_pct", [0, 100])
        if not (lo <= value <= hi):
            raise AdminError(f"soc_percent must be in [{lo}, {hi}], got {value}.")
        return
    if field in ("capacity_kw", "capacity_kwh") and value is not None:
        if value < 0:
            raise AdminError(f"{field} cannot be negative, got {value}.")
        if value > 1_000_000:
            raise AdminError(f"{field} too large, got {value}.")


def get_station_config() -> dict:
    """Full station config (admin view)."""
    return get_config()


def list_resources() -> dict:
    """All resources grouped by category, with ai_modeled flag."""
    return get_config()["resource_catalog"]


def get_resource(resource_id: str) -> dict:
    canonical_id = RESOURCE_ALIASES.get(resource_id.lower(), resource_id)
    for group in get_config()["resource_catalog"].values():
        for res in group:
            if res["id"] in (resource_id, canonical_id):
                return res
    raise AdminError(f"Unknown resource id: {resource_id!r}")


def update_resource(resource_id: str, updates: dict) -> dict:
    """Update a resource's enabled/status/capacity/soc/output/condition. Persists to disk."""
    res = get_resource(resource_id)
    for field, value in updates.items():
        if field not in VALID_FIELDS:
            raise AdminError(f"Cannot update field {field!r}. Allowed: {sorted(VALID_FIELDS)}")
        if field == "online":
            res["enabled"] = bool(value)
            res["status"] = "ONLINE" if value else "OFFLINE"
        if field == "status":
            if str(value).upper() not in VALID_STATUS:
                raise AdminError(
                    f"Invalid status {value!r}. Allowed: {sorted(VALID_STATUS)}"
                )
            value = str(value).upper()
        if field == "enabled":
            if not isinstance(value, bool):
                raise AdminError("'enabled' must be true or false.")
        if field in ("capacity_kw", "capacity_kwh", "soc_percent", "output_kw"):
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise AdminError(f"{field} must be a number, got {value!r}.")
            if field in LIMITED_FIELDS:
                _check_physical_limit(field, value)
        res[field] = value
    save_config()
    return res


def update_station(updates: dict) -> dict:
    """Update station-level fields (name, location) or battery settings."""
    station = get_config()["station"]
    bat_updates = {}
    for field, value in updates.items():
        if field in {"battery_soc", "soc_percent"}:
            bat_updates["soc_percent"] = value
        elif field in {"battery_enabled", "enabled"}:
            bat_updates["enabled"] = bool(value)
            bat_updates["status"] = "ONLINE" if value else "OFFLINE"
        elif field in {"battery_state", "status"}:
            bat_updates["status"] = str(value).upper()
        elif field in {"name", "location"}:
            station[field] = value
        else:
            raise AdminError(f"Cannot update field {field!r}. Allowed: name, location, battery_soc, battery_enabled, battery_state")
    if bat_updates:
        update_resource("battery", bat_updates)
        # Directly sync into running StationCoordinator live simulation
        try:
            from backend.services.station_service import coordinator
            if "soc_percent" in bat_updates:
                coordinator.sim.battery.set_soc(float(bat_updates["soc_percent"]))
                if hasattr(coordinator, "latest_telemetry") and isinstance(coordinator.latest_telemetry, dict):
                    coordinator.latest_telemetry["battery_soc_pct"] = float(bat_updates["soc_percent"])
                    coordinator.latest_telemetry["battery_stored_kwh"] = round(coordinator.sim.battery.stored_kwh, 2)
            if "status" in bat_updates and hasattr(coordinator, "latest_telemetry"):
                coordinator.latest_telemetry["battery_status"] = bat_updates["status"]
        except Exception as e:
            pass
    save_config()
    return get_config()["station"]


def toggle_resource(resource_id: str, online: bool) -> dict:
    """Quick ON/OFF helper used by the UI buttons."""
    status = "ONLINE" if online else "OFFLINE"
    return update_resource(resource_id, {"status": status})


def admin_summary() -> dict:
    """Compact overview for the admin dashboard."""
    cfg = get_config()
    resources = get_resource_config()
    ai_models = {k: v.get("modeled", False) for k, v in cfg.get("ai_models", {}).items()}
    return {
        "station": cfg["station"],
        "ai_models": ai_models,
        "resources_total": len(resources),
        "resources_enabled": sum(1 for r in resources.values() if r.get("enabled")),
        "resources_disabled": sum(1 for r in resources.values() if not r.get("enabled")),
        "resources": resources,
    }


def reload() -> dict:
    """Discard in-memory changes and re-read from disk."""
    reload_config()
    return {"message": "configuration reloaded from disk"}