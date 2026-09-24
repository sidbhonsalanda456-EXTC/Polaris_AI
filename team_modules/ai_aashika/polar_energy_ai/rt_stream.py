import os
import random
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import solar_utils
import failover
from telemetry_history import WEATHER_COLS, RESOURCE_COLS

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "realtime_telemetry.csv")

RES_KEY_MAP = {
    "solar_pv": "solar_kw",
    "wind": "wind_kw",
    "hydropower": "hydropower_kw",
    "geothermal": "geothermal_kw",
    "marine_energy": "marine_energy_kw",
    "biomass_biogas": "biomass_biogas_kw",
    "solar_thermal": "solar_thermal_kw",
    "hydrogen_fuel_cell_available": "h2_kw",
    "battery_available": "battery_kwh",
    "diesel_generator_available": "diesel_kw",
    "chp_available": "chp_kw",
}


def _snap(v, decimals=2):
    return round(max(0.0, float(v)), decimals)


def _caps():
    try:
        from data_generator import load_config
        r = load_config()["resources"]
        return {
            "solar_pv": r["solar_pv"]["capacity_kw"],
            "wind": r["wind"]["capacity_kw"],
            "hydropower": r["hydropower"]["average_kw"],
            "geothermal": r["geothermal"]["average_kw"],
            "marine_energy": r["marine_energy"]["capacity_kw"],
            "biomass_biogas": r["biomass_biogas"]["average_kw"],
            "solar_thermal": r["solar_thermal"]["capacity_kw"],
            "hydrogen_fuel_cell_available": r["hydrogen_fuel_cell"]["capacity_kw"],
            "battery_available": r["battery"]["effective_capacity_kwh"],
            "diesel_generator_available": r["diesel_generator"]["max_kw"],
            "chp_available": r["chp"]["capacity_kw"],
        }
    except Exception:
        return {}


CAPS = _caps()


def _station_lat():
    try:
        from data_generator import load_config
        return load_config()["station"]["latitude"]
    except Exception:
        return -77.84


LAT = _station_lat()


def _forecast_by_hour(forecast):
    keyed = {}
    for f in forecast:
        keyed[f["timestamp_ist"][:13]] = f
    keys = sorted(keyed.keys())
    return keyed, keys


def _past_hour_basis(days=1):
    """AI values for the PAST hours (respect solar/wind/maintenance windows),
    so past minute/second rows use their own hour's state instead of copying
    the current hour (data shifts automatically across hour boundaries).
    Returns ({hour_key: weather_row}, {hour_key: resource_row}).
    """
    try:
        from data_generator import generate_hourly_rows
        wrows, rrows = generate_hourly_rows(days)
    except Exception:
        return {}, {}
    return ({r["timestamp_ist"][:13]: r for r in wrows},
            {r["timestamp_ist"][:13]: r for r in rrows})


def _weather_row(ts, f, current, seconds):
    """One weather reading (IST) derived from the AI forecast + tiny noise."""
    fw = {}
    if f is not None:
        fw = f.get("weather", {})
    temp = fw.get("temperature_c", current.get("temperature_c", -15))
    wind = fw.get("wind_speed_mps", current.get("wind_speed_mps", 8))
    cloud = fw.get("cloud_cover_pct", current.get("cloud_cover_pct", 50))
    irr = fw.get("solar_irradiance_wm2", current.get("solar_irradiance_wm2", 0))
    snow = fw.get("snowfall_mm", current.get("snowfall_mm", 0))

    if seconds:
        temp = temp + random.uniform(-0.4, 0.4)
        wind = max(0, wind + random.uniform(-0.4, 0.4))
        cloud = min(100, max(0, cloud + random.uniform(-2, 2)))
        irr = max(0, irr + random.uniform(-6, 6))
        snow = max(0, snow + random.uniform(-0.02, 0.02))
    else:
        temp = temp + random.uniform(-0.1, 0.1)
        wind = max(0, wind + random.uniform(-0.1, 0.1))

    return {
        "granularity": "second" if seconds else "minute",
        "timestamp_ist": ts.isoformat(),
        "temperature_c": round(temp, 1),
        "feels_like_c": round(temp - random.uniform(1, 4), 1),
        "wind_speed_mps": round(wind, 1),
        "wind_direction_deg": round(current.get("wind_direction_deg", 0), 1),
        "cloud_cover_pct": round(cloud, 1),
        "solar_irradiance_wm2": round(irr, 1),
        "snowfall_mm": round(snow, 2),
        "precipitation_mm": round(current.get("precipitation_mm", 0), 2),
        "humidity_pct": round(current.get("humidity_pct", 70), 1),
        "pressure_hpa": round(current.get("pressure_hpa", 1013), 1),
    }


def _resource_row(ts, f, seconds):
    """One ALL-11-resource reading (IST) derived from the AI forecast."""
    g = {}
    if f is not None:
        g = f.get("predicted_generation_kw", {})
    row = {"granularity": "second" if seconds else "minute", "timestamp_ist": ts.isoformat()}
    for src_key, out_key in RES_KEY_MAP.items():
        v = float(g.get(src_key, 0))
        if v > 0 and seconds:
            v = v + random.uniform(-v * 0.02, v * 0.02)
            cap = CAPS.get(src_key)
            if cap:
                v = min(v, float(cap))
        row[out_key] = _snap(v)
    if not solar_utils.sun_is_up(ts, LAT):
        row["solar_kw"] = 0.0
        row["solar_thermal_kw"] = 0.0
    demand = float(f.get("predicted_demand_kw", 0) if f else 0)
    if demand > 0 and seconds:
        demand = demand + random.uniform(-demand * 0.01, demand * 0.01)
    row["demand_kw"] = round(max(0, demand), 2)
    return row


def _inject_live_seconds(sections, live_seconds):
    """Inject REAL per-second readings (captured one per passing second) into
    sections, replacing any generated/placeholder second rows. Failed-resource
    windows are zeroed exactly like the minute/hour rows."""
    live_seconds = live_seconds or []
    if not live_seconds:
        return sections
    w, r = [], []
    for row in live_seconds:
        wrow = {"granularity": "second", "timestamp_ist": row["timestamp_ist"]}
        rrow = {"granularity": "second", "timestamp_ist": row["timestamp_ist"]}
        for c in WEATHER_COLS:
            wrow[c] = row.get(c)
        for c in RESOURCE_COLS:
            rrow[c] = row.get(c)
        w.append(wrow)
        r.append(rrow)
    apply_failures({"resources": r},
                   sections.get("failover", {}).get("failures", []) or [])
    sections["weather"] = w + [x for x in sections.get("weather", [])
                               if x.get("granularity") != "second"]
    sections["resources"] = r + [x for x in sections.get("resources", [])
                                 if x.get("granularity") != "second"]
    return sections


def build_telemetry(forecast, current=None, start_time=None, live_seconds=None):
    """Build live IST telemetry that NEVER invents future timestamps:
    - seconds   : real readings captured by the live collector, one per passing
                  second, stamped exactly when each second was collected
                  (passed in via live_seconds; generated nowhere else).
    - minutes   : the last 60 completed minutes ending before `now`.
    - hours     : the last 24 completed hours ending before `now`.
    Returns {"weather": [...], "resources": [...], "failover": {...}}."""
    if current is None:
        current = {}
    if start_time is not None:
        now = start_time
    else:
        now = datetime.now(IST)
    keyed, keys = _forecast_by_hour(forecast)
    past_w, past_r = _past_hour_basis()

    def base_entry(ts):
        k = ts.strftime("%Y-%m-%dT%H")
        f = keyed.get(k)
        if f is None:
            rf = past_r.get(k)
            if rf is not None:
                wf = past_w.get(k, {})
                f = {
                    "predicted_generation_kw": {src: rf.get(out, 0)
                                                for src, out in RES_KEY_MAP.items()},
                    "predicted_demand_kw": rf.get("demand_kw", 0),
                    "weather": {
                        "temperature_c": wf.get("temperature_c"),
                        "wind_speed_mps": wf.get("wind_speed_mps"),
                        "cloud_cover_pct": wf.get("cloud_cover_pct"),
                        "solar_irradiance_wm2": wf.get("solar_irradiance_wm2"),
                        "snowfall_mm": wf.get("snowfall_mm"),
                    },
                }
        if f is None and keys:
            f = keyed[keys[0]]
        return f

    weather_rows = []
    resource_rows = []

    # seconds are NOT generated here - they are the real per-passing-second
    # readings captured live (see live_logger.py) and injected via live_seconds.

    # last 60 completed minutes (ending before now, IST)
    for i in range(60, 0, -1):
        ts = now - timedelta(minutes=i)
        f = base_entry(ts)
        weather_rows.append(_weather_row(ts, f, current, seconds=False))
        resource_rows.append(_resource_row(ts, f, seconds=False))

    # last 24 completed hours (ending before now) - PAST telemetry only
    hour_root = now.replace(minute=0, second=0, microsecond=0)
    for i in range(24, 0, -1):
        ts = hour_root - timedelta(hours=i)
        f = base_entry(ts) or {}
        fw = f.get("weather", {})
        temp = fw.get("temperature_c", current.get("temperature_c", -15))
        weather_rows.append({
            "granularity": "hour",
            "timestamp_ist": ts.isoformat(),
            "temperature_c": round(temp, 1),
            "feels_like_c": round(temp - random.uniform(1, 4), 1),
            "wind_speed_mps": fw.get("wind_speed_mps",
                                     current.get("wind_speed_mps", 0)),
            "wind_direction_deg": current.get("wind_direction_deg", 0),
            "cloud_cover_pct": fw.get("cloud_cover_pct",
                                      current.get("cloud_cover_pct", 0)),
            "solar_irradiance_wm2": fw.get("solar_irradiance_wm2",
                                           current.get("solar_irradiance_wm2", 0)),
            "snowfall_mm": fw.get("snowfall_mm", current.get("snowfall_mm", 0)),
            "precipitation_mm": current.get("precipitation_mm", 0),
            "humidity_pct": current.get("humidity_pct", 70),
            "pressure_hpa": current.get("pressure_hpa", 1013),
        })
        hourly_resource = {"granularity": "hour",
                           "timestamp_ist": ts.isoformat()}
        g = f.get("predicted_generation_kw", {})
        for src, out in RES_KEY_MAP.items():
            hourly_resource[out] = _snap(float(g.get(src, 0)))
        hourly_resource["demand_kw"] = round(float(f.get("predicted_demand_kw", 0)), 2)
        resource_rows.append(hourly_resource)

    sections = {"weather": weather_rows, "resources": resource_rows}

    failures = failover.pick_failures(forecast, now) if forecast else []
    if failures:
        apply_failures(sections, failures)
        sections["failover"] = {
            "failures": failures,
            "rows": failover.compute_failover(forecast, failures),
        }
    else:
        sections["failover"] = {"failures": [], "rows": []}

    if live_seconds:
        _inject_live_seconds(sections, live_seconds)

    return sections


def apply_failures(sections, failures):
    """Zero out the failed resource across all telemetry rows inside its window.
    Mutates sections in place; returns the sections dict."""
    if not failures:
        return sections
    for row in sections.get("resources", []):
        ts = datetime.fromisoformat(row["timestamp_ist"])
        for fr in failures:
            if fr["from_dt"] <= ts < fr["to_dt"]:
                col = RES_KEY_MAP.get(fr["src_key"])
                if col:
                    row[col] = 0.0
    return sections


def save_telemetry_csv(sections):
    """Legacy helper: flatten both sections. No file is written anymore -
    the single data store is data/ai_telemetry_history.xlsx."""
    weather = pd.DataFrame(sections["weather"])
    resources = pd.DataFrame(sections["resources"])
    if weather.empty:
        return None

    w = weather.rename(columns={"granularity": "w_g"})
    r = resources.rename(columns={"granularity": "r_g", "timestamp_ist": "ts"})
    merged = pd.merge(w, r, left_on="timestamp_ist", right_on="ts", how="left") \
        .drop(columns=["ts", "r_g"])
    return merged


if __name__ == "__main__":
    sections = build_telemetry([])
    print(f"Weather rows: {len(sections['weather'])}")
    print(f"Resource rows: {len(sections['resources'])}")