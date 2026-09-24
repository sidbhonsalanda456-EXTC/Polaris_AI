import json
import os
import random
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import solar_utils

IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "shared", "station_config.json")
DATA_PATH = os.path.join(BASE_DIR, "data", "historical_weather_energy.csv")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def get_season(month):
    if month in [12, 1, 2]:
        return "summer"
    elif month in [3, 4, 5]:
        return "autumn"
    elif month in [6, 7, 8]:
        return "winter"
    else:
        return "spring"


def generate_weather_for_hour(hour, day_of_year, config):
    station = config["station"]
    lat = abs(station["latitude"])

    seasonal_temp_offset = -15 + 10 * math.cos(2 * math.pi * (day_of_year - 1) / 365)
    diurnal_temp = 3 * math.sin(2 * math.pi * (hour - 6) / 24)

    temperature = seasonal_temp_offset + diurnal_temp + random.gauss(0, 2)
    feels_like = temperature - random.uniform(1, 5)

    wind_speed = max(0, 8 + 5 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 3))
    wind_direction = random.uniform(0, 360)

    cloud_cover = max(0, min(100, 50 + 30 * math.sin(2 * math.pi * (day_of_year + hour) / 48) + random.gauss(0, 15)))

    elev = solar_utils.solar_elevation_doy_deg(day_of_year, hour, station["latitude"])
    solar_irradiance = solar_utils.solar_irradiance_base(elev, cloud_cover) + random.gauss(0, 30)
    solar_irradiance = max(0, solar_irradiance)

    snowfall = max(0, random.gauss(0.5, 1)) if temperature < 0 and cloud_cover > 60 else 0
    precipitation = max(0, random.gauss(0.3, 0.5)) if cloud_cover > 50 else 0
    humidity = max(20, min(100, 70 + 20 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 10)))
    pressure = max(980, min(1040, 1013 + random.gauss(0, 5)))

    return {
        "temperature_c": round(temperature, 1),
        "feels_like_c": round(feels_like, 1),
        "wind_speed_mps": round(wind_speed, 1),
        "wind_direction_deg": round(wind_direction, 1),
        "cloud_cover_pct": round(cloud_cover, 1),
        "solar_irradiance_wm2": round(solar_irradiance, 1),
        "snowfall_mm": round(snowfall, 2),
        "precipitation_mm": round(precipitation, 2),
        "humidity_pct": round(humidity, 1),
        "pressure_hpa": round(pressure, 1),
    }


def calculate_solar(weather, config):
    capacity = config["resources"]["solar_pv"]["capacity_kw"]
    hour = weather["hour"]
    doy = weather.get("day_of_year", datetime.now(IST).timetuple().tm_yday)
    elev = solar_utils.solar_elevation_doy_deg(doy, hour, config["station"]["latitude"])
    if elev <= 0:
        return 0.0

    irradiance_factor = weather["solar_irradiance_wm2"] / 1000.0
    cloud_penalty = 1 - (weather["cloud_cover_pct"] / 100) * 0.6
    snow_penalty = max(0.5, 1 - weather["snowfall_mm"] * 0.1)
    temp_factor = max(0.7, 1 - abs(weather["temperature_c"] - 25) * 0.005)

    solar = capacity * irradiance_factor * cloud_penalty * snow_penalty * temp_factor
    return round(max(0, min(capacity, solar + random.gauss(0, 5))), 2)


def calculate_wind(weather, config):
    capacity = config["resources"]["wind"]["capacity_kw"]
    cut_in = config["resources"]["wind"]["cut_in_mps"]
    rated = config["resources"]["wind"]["rated_mps"]
    cut_out = config["resources"]["wind"]["cut_out_mps"]

    ws = weather["wind_speed_mps"]
    if ws < cut_in or ws > cut_out:
        return 0.0
    if ws >= rated:
        return round(capacity, 2)

    wind_factor = (ws - cut_in) / (rated - cut_in)
    wind_out = capacity * wind_factor + random.gauss(0, 3)
    return round(max(0, min(capacity, wind_out)), 2)


def calculate_demand(weather, config):
    base = config["loads"]["base_total_demand_kw"]
    heating = config["loads"]["heating_kw"]
    passive_reduction = config["resources"]["passive_solar_efficiency"]["demand_reduction_percent"] / 100

    temp = weather["temperature_c"]
    heating_factor = max(0.5, 1 + (0 - temp) * 0.02)

    hourly_factor = 1 + 0.1 * math.sin(2 * math.pi * (weather["hour"] - 6) / 24)

    demand = (base * heating_factor + heating * heating_factor) * hourly_factor
    demand = demand * (1 - passive_reduction * max(0, weather["solar_irradiance_wm2"] / 800))

    return round(max(50, demand + random.gauss(0, 5)), 2)


def in_fault_window(hour, window):
    parts = window.split("-")
    s = int(parts[0].split(":")[0])
    e = int(parts[1].split(":")[0])
    return s <= hour <= e


def compute_resources(weather, config):
    """Estimated readings for ALL 11 resources + demand for one hour.
    weather must include an 'hour' key.
    """
    r = config["resources"]
    faults = config.get("fault_windows_ist", {})

    solar_kw = calculate_solar(weather, config)
    wind_kw = calculate_wind(weather, config)
    demand_kw = calculate_demand(weather, config)
    hour = weather["hour"]

    hydro = 0.0
    if "hydro_unavailable" in faults and in_fault_window(hour, faults["hydro_unavailable"]):
        hydro = 0.0
    elif "hydropower" in r and "average_kw" in r["hydropower"]:
        hydro = r["hydropower"]["average_kw"]

    diesel = 0.0
    if "diesel_unavailable" in faults and in_fault_window(hour, faults["diesel_unavailable"]):
        diesel = 0.0
    elif "diesel_generator" in r and "max_kw" in r["diesel_generator"]:
        diesel = r["diesel_generator"]["max_kw"]

    solar_thermal = 0.0
    if 9 <= hour <= 16:
        solar_thermal = r["solar_thermal"]["capacity_kw"]

    return {
        "solar_kw": round(solar_kw, 2),
        "wind_kw": round(wind_kw, 2),
        "hydropower_kw": round(hydro, 2),
        "geothermal_kw": round(r["geothermal"]["average_kw"], 2),
        "marine_energy_kw": round(r["marine_energy"]["capacity_kw"], 2),
        "biomass_biogas_kw": round(r["biomass_biogas"]["average_kw"], 2),
        "solar_thermal_kw": round(solar_thermal, 2),
        "h2_kw": round(r["hydrogen_fuel_cell"]["capacity_kw"], 2),
        "battery_kwh": round(r["battery"]["effective_capacity_kwh"], 2),
        "diesel_kw": round(diesel, 2),
        "chp_kw": round(r["chp"]["capacity_kw"], 2),
        "demand_kw": round(demand_kw, 2),
    }


def generate_hourly_rows(days):
    """Reconstructed hourly rows (weather + resources) for the past N days.
    Returns (weather_rows, resource_rows) - every row is IST timestamped.
    """
    config = load_config()
    now = datetime.now(IST)
    weather_rows, resource_rows = [], []

    for i in range(days * 24, 0, -1):
        t = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
        w = generate_weather_for_hour(t.hour, t.timetuple().tm_yday, config)
        w["hour"] = t.hour
        w["day_of_year"] = t.timetuple().tm_yday
        weather_rows.append({
            "timestamp_ist": t.isoformat(),
            "temperature_c": w["temperature_c"],
            "feels_like_c": w["feels_like_c"],
            "wind_speed_mps": w["wind_speed_mps"],
            "wind_direction_deg": w["wind_direction_deg"],
            "cloud_cover_pct": w["cloud_cover_pct"],
            "solar_irradiance_wm2": w["solar_irradiance_wm2"],
            "snowfall_mm": w["snowfall_mm"],
            "precipitation_mm": w["precipitation_mm"],
            "humidity_pct": w["humidity_pct"],
            "pressure_hpa": w["pressure_hpa"],
        })
        resource_rows.append({
            "timestamp_ist": t.isoformat(),
            **compute_resources(w, config),
        })

    return weather_rows, resource_rows


def generate_dataset():
    config = load_config()
    start_date = datetime(2025, 9, 9, 0, 0, tzinfo=IST)
    end_date = datetime(2026, 9, 8, 23, 0, tzinfo=IST)

    records = []
    current = start_date

    while current <= end_date:
        day_of_year = current.timetuple().tm_yday
        hour = current.hour
        month = current.month

        weather = generate_weather_for_hour(hour, day_of_year, config)
        weather["hour"] = hour
        weather["day_of_year"] = day_of_year

        solar = calculate_solar(weather, config)
        wind = calculate_wind(weather, config)
        demand = calculate_demand(weather, config)

        record = {
            "timestamp_ist": current.isoformat(),
            "temperature_c": weather["temperature_c"],
            "feels_like_c": weather["feels_like_c"],
            "wind_speed_mps": weather["wind_speed_mps"],
            "wind_direction_deg": weather["wind_direction_deg"],
            "cloud_cover_pct": weather["cloud_cover_pct"],
            "solar_irradiance_wm2": weather["solar_irradiance_wm2"],
            "snowfall_mm": weather["snowfall_mm"],
            "precipitation_mm": weather["precipitation_mm"],
            "humidity_pct": weather["humidity_pct"],
            "pressure_hpa": weather["pressure_hpa"],
            "solar_actual_kw": solar,
            "wind_actual_kw": wind,
            "demand_actual_kw": demand,
        }
        records.append(record)
        current += timedelta(hours=1)

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    print(f"Dataset saved: {DATA_PATH}")
    print(f"Records: {len(df)}")
    print(f"Date range: {df['timestamp_ist'].iloc[0]} to {df['timestamp_ist'].iloc[-1]}")
    return df


if __name__ == "__main__":
    generate_dataset()
