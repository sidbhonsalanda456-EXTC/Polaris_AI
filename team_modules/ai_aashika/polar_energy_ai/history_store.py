import os
import json
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(BASE_DIR, "data", "ai_history.json")
BACKFILL_DAYS = 7

WEATHER_FIELDS = [
    "temperature_c", "feels_like_c", "wind_speed_mps", "wind_direction_deg",
    "cloud_cover_pct", "solar_irradiance_wm2", "snowfall_mm",
    "precipitation_mm", "humidity_pct", "pressure_hpa",
]
RESOURCE_FIELDS = [
    "solar_kw", "wind_kw", "hydropower_kw", "geothermal_kw",
    "marine_energy_kw", "biomass_biogas_kw", "solar_thermal_kw",
    "h2_kw", "battery_kwh", "diesel_kw", "chp_kw", "demand_kw",
]


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            h = json.load(f)
    else:
        h = {}
    h.setdefault("created_at_ist", None)
    h.setdefault("last_updated_ist", None)
    h["source"] = "polar station live sensor feed"
    h.setdefault("backfill_days", BACKFILL_DAYS)
    h.setdefault("resolution", {"seconds": 1, "minutes": 1, "hours": 1})
    h.setdefault("resources", [])
    h.setdefault("weather", [])
    return h


def save_history(h):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    from safe_write import write_json
    write_json(h, HISTORY_PATH)


def seed_history_if_empty():
    """On first run, back-fill recent hourly station data so the models can learn.
    After that the archive ONLY grows with live data appended every run.
    """
    h = load_history()
    if h["resources"] or h["weather"]:
        return h, False

    from data_generator import generate_hourly_rows
    weather_rows, resource_rows = generate_hourly_rows(BACKFILL_DAYS)
    h["resources"] = resource_rows
    h["weather"] = weather_rows
    if h["created_at_ist"] is None:
        h["created_at_ist"] = datetime.now(IST).isoformat()
    h["last_updated_ist"] = datetime.now(IST).isoformat()
    save_history(h)
    return h, True


def append_rows(h, weather_rows, resource_rows):
    """Append new live readings to both sections (deduplicated by timestamp)."""
    seen_w = {r["timestamp_ist"] for r in h["weather"]}
    seen_r = {r["timestamp_ist"] for r in h["resources"]}

    added_weather = 0
    for r in weather_rows:
        if r["timestamp_ist"] not in seen_w:
            h["weather"].append(r)
            seen_w.add(r["timestamp_ist"])
            added_weather += 1

    added_resources = 0
    for r in resource_rows:
        if r["timestamp_ist"] not in seen_r:
            h["resources"].append(r)
            seen_r.add(r["timestamp_ist"])
            added_resources += 1

    h["last_updated_ist"] = datetime.now(IST).isoformat()
    save_history(h)
    return added_weather, added_resources


def to_training_dataframe(h):
    """Merge the archive's two sections into the training table the
    ML models understand (same column names as before)."""
    weather = pd.DataFrame(h.get("weather", []))
    resources = pd.DataFrame(h.get("resources", []))
    if weather.empty or resources.empty:
        return None

    m = pd.merge(weather, resources, on="timestamp_ist", how="inner")
    if m.empty:
        return None

    m = m.sort_values("timestamp_ist").reset_index(drop=True)
    m = m.rename(columns={
        "solar_kw": "solar_actual_kw",
        "wind_kw": "wind_actual_kw",
        "demand_kw": "demand_actual_kw",
    })

    for col in WEATHER_FIELDS + ["solar_actual_kw", "wind_actual_kw", "demand_actual_kw"]:
        if col not in m.columns:
            m[col] = 0.0

    return m[["timestamp_ist"] + WEATHER_FIELDS + ["solar_actual_kw", "wind_actual_kw", "demand_actual_kw"]]


def history_stats(h):
    return {
        "weather_rows": len(h.get("weather", [])),
        "resource_rows": len(h.get("resources", [])),
        "created_at_ist": h.get("created_at_ist"),
        "last_updated_ist": h.get("last_updated_ist"),
        "backfill_days": h.get("backfill_days"),
    }


if __name__ == "__main__":
    h, seeded = seed_history_if_empty()
    stats = history_stats(h)
    print(f"Seeded: {seeded}")
    print(f"Weather readings: {stats['weather_rows']}")
    print(f"Resource readings: {stats['resource_rows']}")
    print(f"Archive: {HISTORY_PATH}")