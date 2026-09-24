import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import solar_utils

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "shared", "station_config.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "output", "ai_forecast.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def get_season(month):
    if month in [12, 1, 2]:
        return 0
    elif month in [3, 4, 5]:
        return 1
    elif month in [6, 7, 8]:
        return 2
    else:
        return 3


def prepare_features(weather_entry, prev_solar=0, prev_wind=0, prev_demand=100, rolling_demand=100, rolling_wind=0):
    ts = datetime.fromisoformat(weather_entry["timestamp_ist"])
    hour = ts.hour
    month = ts.month
    season = get_season(month)
    day_of_week = ts.weekday()

    wind_dir = weather_entry.get("wind_direction_deg", 0)
    wind_sin = np.sin(np.radians(wind_dir))
    wind_cos = np.cos(np.radians(wind_dir))

    severity = (
        (weather_entry.get("wind_speed_mps", 0) / 25) * 0.3 +
        (weather_entry.get("snowfall_mm", 0) / 10) * 0.3 +
        (max(0, 50 - weather_entry.get("temperature_c", 0)) / 50) * 0.2 +
        (weather_entry.get("cloud_cover_pct", 0) / 100) * 0.2
    )

    is_solar_active = 1 if solar_utils.sun_is_up(ts, load_config()["station"]["latitude"]) else 0

    solar_features = np.array([[
        weather_entry.get("solar_irradiance_wm2", 0),
        weather_entry.get("cloud_cover_pct", 0),
        weather_entry.get("temperature_c", 0),
        weather_entry.get("snowfall_mm", 0),
        hour, month, season, prev_solar, is_solar_active
    ]])

    wind_features = np.array([[
        weather_entry.get("wind_speed_mps", 0),
        wind_sin, wind_cos,
        weather_entry.get("temperature_c", 0),
        weather_entry.get("pressure_hpa", 1013),
        weather_entry.get("snowfall_mm", 0),
        hour, prev_wind
    ]])

    demand_features = np.array([[
        weather_entry.get("temperature_c", 0),
        weather_entry.get("feels_like_c", 0),
        hour, day_of_week, month,
        weather_entry.get("snowfall_mm", 0),
        severity, prev_demand, rolling_demand
    ]])

    return solar_features, wind_features, demand_features


def apply_fault_conditions(hour, config):
    conditions = {
        "wind": True,
        "hydropower": True,
        "diesel_generator": True,
    }
    faults = config.get("fault_windows_ist", {})
    if "wind_unavailable" in faults:
        parts = faults["wind_unavailable"].split("-")
        s, e = int(parts[0].split(":")[0]), int(parts[1].split(":")[0])
        if s <= hour <= e:
            conditions["wind"] = False
    if "hydro_unavailable" in faults:
        parts = faults["hydro_unavailable"].split("-")
        s, e = int(parts[0].split(":")[0]), int(parts[1].split(":")[0])
        if s <= hour <= e:
            conditions["hydropower"] = False
    if "diesel_unavailable" in faults:
        parts = faults["diesel_unavailable"].split("-")
        s, e = int(parts[0].split(":")[0]), int(parts[1].split(":")[0])
        if s <= hour <= e:
            conditions["diesel_generator"] = False
    return conditions


def apply_disaster_conditions(hour, config):
    disasters = config.get("disaster_windows_ist", {})
    applied = []

    for name, info in disasters.items():
        window = info["time"]
        parts = window.split("-")
        s, e = int(parts[0].split(":")[0]), int(parts[1].split(":")[0])
        if s <= hour <= e:
            applied.append({"name": name, "info": info})
    return applied


def recommend_resource_mix(entry):
    """AI picks the best-suitable resource(s) for this hour:
    rank every AVAILABLE resource by its predicted output, then keep
    adding top resources (renewables first anyway since they are ranked by
    predicted generation) until the predicted demand is covered.
    """
    avail = entry.get("availability", {})
    gen = entry.get("predicted_generation_kw", {})
    demand = entry.get("predicted_demand_kw", 0)

    names = {
        "geothermal": "Geothermal", "biomass_biogas": "Biomass",
        "marine_energy": "Marine", "wind": "Wind", "hydropower": "Hydro",
        "solar_pv": "Solar PV", "solar_thermal": "Solar Thermal",
        "hydrogen_fuel_cell": "H2 Cell", "battery": "Battery",
        "chp": "CHP", "diesel_generator": "Diesel",
    }
    categories = {
        "geothermal": "steady baseload", "biomass_biogas": "steady baseload",
        "marine_energy": "steady baseload", "wind": "clean renewable",
        "hydropower": "clean renewable", "solar_pv": "clean renewable",
        "solar_thermal": "clean renewable", "hydrogen_fuel_cell": "clean storage",
        "battery": "energy storage", "chp": "cogeneration",
        "diesel_generator": "fossil backup",
    }

    candidates = []
    valid = {}
    gen_keys = ["wind", "solar_pv", "hydropower", "geothermal", "biomass_biogas",
                "marine_energy", "solar_thermal", "hydrogen_fuel_cell", "chp",
                "diesel_generator"]
    for key in gen_keys:
        if avail.get(key) != "available":
            continue
        value = float(gen.get(key, 0) or gen.get(key + "_available", 0))
        if value > 0:
            valid[key] = value

    # Preference order:
    # 1) free/clean renewables that are actively producing (highest output first)
    # 2) steady renewable baseload (geothermal, biomass, marine)
    # 3) clean storage (H2 cell), cogeneration
    # 4) fossil backup (diesel) - LAST resort
    intermittent = [k for k in ["wind", "solar_pv", "hydropower", "solar_thermal"] if k in valid]
    intermittent.sort(key=lambda k: -valid[k])
    ordered = (intermittent +
               [k for k in ["geothermal", "biomass_biogas", "marine_energy"] if k in valid] +
               [k for k in ["hydrogen_fuel_cell", "chp"] if k in valid] +
               [k for k in ["diesel_generator"] if k in valid])
    if not ordered:
        ordered = [k for k in valid]
        ordered.sort(key=lambda k: -valid[k])

    for key in ordered:
        candidates.append({
            "name": names[key], "value_kw": round(valid[key], 1), "category": categories[key],
        })

    chosen = []
    covered = 0.0
    for c in candidates:
        chosen.append(c)
        covered += c["value_kw"]
        if covered >= demand:
            break

    battery_ready = avail.get("battery") == "available"
    if covered >= demand:
        strategy = "RENEWABLE-FIRST MIX (demand covered)"
    elif battery_ready:
        strategy = "RENEWABLES + BATTERY RESERVE NEEDED"
    else:
        strategy = "RENEWABLES + BACKUP NEEDED (deficit covered by storage/diesel)"

    primary = chosen[0] if chosen else {"name": "None", "value_kw": 0, "category": "no resource available"}
    secondary = chosen[1] if len(chosen) > 1 else {"name": "-", "value_kw": 0, "category": "-"}
    tertiary = chosen[2] if len(chosen) > 2 else {"name": "-", "value_kw": 0, "category": "-"}

    return {
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "coverage_kw": round(covered, 1),
        "battery_reserve_ready": battery_ready,
        "strategy": strategy,
    }


def generate_24h_forecast(weather_cache, solar_model, wind_model, demand_model, solar_metrics, wind_metrics, demand_metrics):
    config = load_config()

    hourly = weather_cache.get("hourly", [])
    if not hourly:
        return {"error": "No hourly forecast data available"}

    forecasts = []
    prev_solar = 0
    prev_wind = 0
    prev_demand = config["loads"]["base_total_demand_kw"]
    rolling_demand = prev_demand
    rolling_wind = 0

    demand_window = []
    wind_window = []

    for i, weather in enumerate(hourly[:24]):
        ts = datetime.fromisoformat(weather["timestamp_ist"])
        hour = ts.hour

        solar_f, wind_f, demand_f = prepare_features(
            weather, prev_solar, prev_wind, prev_demand,
            rolling_demand, rolling_wind
        )

        predicted_solar = max(0, float(solar_model.predict(solar_f)[0]))
        predicted_solar = min(predicted_solar, config["resources"]["solar_pv"]["capacity_kw"])
        if not solar_utils.sun_is_up(ts, config["station"]["latitude"]):
            predicted_solar = 0.0

        predicted_wind = max(0, float(wind_model.predict(wind_f)[0]))
        predicted_wind = min(predicted_wind, config["resources"]["wind"]["capacity_kw"])
        ws_hour = weather.get("wind_speed_mps", 0)
        cut_in = config["resources"]["wind"]["cut_in_mps"]
        cut_out = config["resources"]["wind"]["cut_out_mps"]
        if ws_hour < cut_in or ws_hour > cut_out:
            predicted_wind = 0.0

        predicted_demand = max(50, float(demand_model.predict(demand_f)[0]))

        faults = apply_fault_conditions(hour, config)
        if not faults["wind"]:
            predicted_wind = 0
        if not faults["hydropower"]:
            hydro_available = 0
        else:
            hydro_available = config["resources"]["hydropower"]["average_kw"]

        diesel_available = config["resources"]["diesel_generator"]["max_kw"] if faults["diesel_generator"] else 0

        disasters = apply_disaster_conditions(hour, config)
        disaster_desc = None
        for d in disasters:
            info = d["info"]
            if "wind_derate_percent" in info:
                predicted_wind *= (1 - info["wind_derate_percent"] / 100)
            if "solar_derate_percent" in info:
                predicted_solar *= (1 - info["solar_derate_percent"] / 100)
            if "marine_derate_percent" in info:
                pass
            disaster_desc = d["name"]

        from risk_alerts import generate_all_alerts
        alerts = generate_all_alerts(weather, predicted_solar, predicted_wind, predicted_demand)

        availability = {
            "solar_pv": "available",
            "wind": "available" if faults["wind"] else "not available",
            "hydropower": "available" if faults["hydropower"] else "not available",
            "geothermal": "available",
            "marine_energy": "available",
            "biomass_biogas": "available",
            "solar_thermal": "available" if solar_utils.sun_is_up(ts, config["station"]["latitude"]) else "not available",
            "hydrogen_fuel_cell": "available",
            "battery": "available",
            "diesel_generator": "available" if faults["diesel_generator"] else "not available",
            "chp": "available",
        }

        resource_forecast = {
            "solar_pv": round(predicted_solar, 2),
            "wind": round(predicted_wind, 2),
            "hydropower": round(hydro_available, 2),
            "geothermal": round(config["resources"]["geothermal"]["average_kw"], 2),
            "marine_energy": round(config["resources"]["marine_energy"]["capacity_kw"], 2),
            "biomass_biogas": round(config["resources"]["biomass_biogas"]["average_kw"], 2),
            "solar_thermal": round(config["resources"]["solar_thermal"]["capacity_kw"], 2) if solar_utils.sun_is_up(ts, config["station"]["latitude"]) else 0,
            "hydrogen_fuel_cell_available": round(config["resources"]["hydrogen_fuel_cell"]["capacity_kw"], 2),
            "battery_available": round(config["resources"]["battery"]["effective_capacity_kwh"], 2),
            "diesel_generator_available": round(diesel_available, 2),
            "chp_available": round(config["resources"]["chp"]["capacity_kw"], 2),
        }

        forecast_entry = {
            "timestamp_ist": weather["timestamp_ist"],
            "weather": {
                "temperature_c": round(weather.get("temperature_c", 0), 1),
                "wind_speed_mps": round(weather.get("wind_speed_mps", 0), 1),
                "cloud_cover_pct": round(weather.get("cloud_cover_pct", 0), 1),
                "solar_irradiance_wm2": round(weather.get("solar_irradiance_wm2", 0), 1),
                "snowfall_mm": round(weather.get("snowfall_mm", 0), 2),
            },
            "predicted_generation_kw": resource_forecast,
            "predicted_demand_kw": round(predicted_demand, 2),
            "availability": availability,
            "recommended_resources": recommend_resource_mix({
                "availability": availability,
                "predicted_generation_kw": resource_forecast,
                "predicted_demand_kw": round(predicted_demand, 2),
            }),
            "disaster_forecast": disaster_desc,
            "risk_alerts": alerts,
            "model_confidence_percent": {
                "solar": round(solar_metrics.get("test", {}).get("r2", 0) * 100, 1),
                "wind": round(wind_metrics.get("test", {}).get("r2", 0) * 100, 1),
                "demand": round(demand_metrics.get("test", {}).get("r2", 0) * 100, 1),
            },
        }
        forecasts.append(forecast_entry)

        prev_solar = predicted_solar
        prev_wind = predicted_wind
        prev_demand = predicted_demand
        demand_window.append(predicted_demand)
        wind_window.append(predicted_wind)
        if len(demand_window) > 24:
            demand_window.pop(0)
            wind_window.pop(0)
        rolling_demand = np.mean(demand_window)
        rolling_wind = np.mean(wind_window)

    metrics_path = os.path.join(BASE_DIR, "output", "model_metrics.json")
    model_metrics = {}
    if os.path.exists(metrics_path):
        with open(metrics_path, "r") as f:
            model_metrics = json.load(f)

    result = {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "weather_source": weather_cache.get("source", "unknown"),
        "forecast": forecasts,
        "model_metrics": model_metrics,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    from solar_model import load_solar_model
    from wind_model import load_wind_model
    from demand_model import load_demand_model
    from weather_service import get_weather

    solar_m = load_solar_model()
    wind_m = load_wind_model()
    demand_m = load_demand_model()
    if not all([solar_m, wind_m, demand_m]):
        print("Models not found. Run train_models.py first.")
        exit(1)

    metrics_path = os.path.join(BASE_DIR, "output", "model_metrics.json")
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    weather = get_weather()
    result = generate_24h_forecast(weather, solar_m, wind_m, demand_m, metrics["solar"], metrics["wind"], metrics["demand"])
    print(f"Forecast generated for {len(result['forecast'])} hours")
    print(f"Saved to {OUTPUT_PATH}")
