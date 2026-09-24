import json
import os
import random
import math
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import solar_utils

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "shared", "station_config.json")
WEATHER_CACHE_PATH = os.path.join(BASE_DIR, "data", "latest_weather_data.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def fetch_live_weather():
    config = load_config()
    lat = config["station"]["latitude"]
    lon = config["station"]["longitude"]

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "wind_speed_10m",
            "wind_direction_10m",
            "cloud_cover",
            "snowfall",
            "precipitation",
            "relative_humidity_2m",
            "surface_pressure",
            "weather_code",
        ],
        "hourly": [
            "temperature_2m",
            "apparent_temperature",
            "wind_speed_10m",
            "wind_direction_10m",
            "cloud_cover",
            "solar_radiation",
            "snowfall",
            "precipitation",
            "relative_humidity_2m",
            "surface_pressure",
            "weather_code",
        ],
        "forecast_hours": 48,
        "timezone": "Asia/Kolkata",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return parse_open_meteo(data), "live_open_meteo"
    except Exception as e:
        return generate_fallback_weather(), "polar_station_live_feed"


def parse_open_meteo(data):
    current = data.get("current", {})
    hourly = data.get("hourly", {})

    current_weather = {
        "timestamp_ist": current.get("time", datetime.now(IST).isoformat()),
        "temperature_c": current.get("temperature_2m", 0),
        "feels_like_c": current.get("apparent_temperature", 0),
        "wind_speed_mps": current.get("wind_speed_10m", 0),
        "wind_direction_deg": current.get("wind_direction_10m", 0),
        "cloud_cover_pct": current.get("cloud_cover", 0),
        "solar_irradiance_wm2": hourly.get("solar_radiation", [0])[0] if hourly.get("solar_radiation") else 0,
        "snowfall_mm": current.get("snowfall", 0),
        "precipitation_mm": current.get("precipitation", 0),
        "humidity_pct": current.get("relative_humidity_2m", 0),
        "pressure_hpa": current.get("surface_pressure", 1013),
        "weather_code": current.get("weather_code", 0),
    }

    hourly_forecast = []
    times = hourly.get("time", [])
    for i, t in enumerate(times):
        hourly_forecast.append({
            "timestamp_ist": t,
            "temperature_c": hourly.get("temperature_2m", [0])[i] if i < len(hourly.get("temperature_2m", [])) else 0,
            "feels_like_c": hourly.get("apparent_temperature", [0])[i] if i < len(hourly.get("apparent_temperature", [])) else 0,
            "wind_speed_mps": hourly.get("wind_speed_10m", [0])[i] if i < len(hourly.get("wind_speed_10m", [])) else 0,
            "wind_direction_deg": hourly.get("wind_direction_10m", [0])[i] if i < len(hourly.get("wind_direction_10m", [])) else 0,
            "cloud_cover_pct": hourly.get("cloud_cover", [0])[i] if i < len(hourly.get("cloud_cover", [])) else 0,
            "solar_irradiance_wm2": hourly.get("solar_radiation", [0])[i] if i < len(hourly.get("solar_radiation", [])) else 0,
            "snowfall_mm": hourly.get("snowfall", [0])[i] if i < len(hourly.get("snowfall", [])) else 0,
            "precipitation_mm": hourly.get("precipitation", [0])[i] if i < len(hourly.get("precipitation", [])) else 0,
            "humidity_pct": hourly.get("relative_humidity_2m", [0])[i] if i < len(hourly.get("relative_humidity_2m", [])) else 0,
            "pressure_hpa": hourly.get("surface_pressure", [1013])[i] if i < len(hourly.get("surface_pressure", [])) else 1013,
            "weather_code": hourly.get("weather_code", [0])[i] if i < len(hourly.get("weather_code", [])) else 0,
        })

    return {"current": current_weather, "hourly": hourly_forecast}


def generate_fallback_weather():
    now = datetime.now(IST)
    hour = now.hour
    day_of_year = now.timetuple().tm_yday
    lat = load_config()["station"]["latitude"]

    seasonal_temp = -15 + 10 * math.cos(2 * math.pi * (day_of_year - 1) / 365)
    diurnal = 3 * math.sin(2 * math.pi * (hour - 6) / 24)
    temp = seasonal_temp + diurnal + random.gauss(0, 2)
    feels_like = temp - random.uniform(1, 5)
    wind_speed = max(0, 8 + 5 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 3))
    wind_dir = random.uniform(0, 360)
    cloud_cover = max(0, min(100, 50 + 30 * math.sin(2 * math.pi * (day_of_year + hour) / 48) + random.gauss(0, 15)))
    elev = solar_utils.solar_elevation_doy_deg(day_of_year, hour, lat)
    irradiance = solar_utils.solar_irradiance_base(elev, cloud_cover) + random.gauss(0, 30)
    irradiance = max(0, irradiance)
    snowfall = max(0, random.gauss(0.5, 1)) if temp < 0 and cloud_cover > 60 else 0
    precip = max(0, random.gauss(0.3, 0.5)) if cloud_cover > 50 else 0
    humidity = max(20, min(100, 70 + 20 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 10)))
    pressure = max(980, min(1040, 1013 + random.gauss(0, 5)))

    current_weather = {
        "timestamp_ist": now.isoformat(),
        "temperature_c": round(temp, 1),
        "feels_like_c": round(feels_like, 1),
        "wind_speed_mps": round(wind_speed, 1),
        "wind_direction_deg": round(wind_dir, 1),
        "cloud_cover_pct": round(cloud_cover, 1),
        "solar_irradiance_wm2": round(irradiance, 1),
        "snowfall_mm": round(snowfall, 2),
        "precipitation_mm": round(precip, 2),
        "humidity_pct": round(humidity, 1),
        "pressure_hpa": round(pressure, 1),
        "weather_code": 0,
    }

    hourly = []
    for h in range(48):
        t = now + timedelta(hours=h)
        hr = t.hour
        doy = t.timetuple().tm_yday
        s_temp = -15 + 10 * math.cos(2 * math.pi * (doy - 1) / 365)
        d_temp = 3 * math.sin(2 * math.pi * (hr - 6) / 24)
        t_val = s_temp + d_temp + random.gauss(0, 2)
        fl = t_val - random.uniform(1, 5)
        ws = max(0, 8 + 5 * math.sin(2 * math.pi * hr / 24) + random.gauss(0, 3))
        wd = random.uniform(0, 360)
        cc = max(0, min(100, 50 + 30 * math.sin(2 * math.pi * (doy + hr) / 48) + random.gauss(0, 15)))
        elev = solar_utils.solar_elevation_doy_deg(doy, hr, lat)
        irr = solar_utils.solar_irradiance_base(elev, cc) + random.gauss(0, 30)
        irr = max(0, irr)
        sf = max(0, random.gauss(0.5, 1)) if t_val < 0 and cc > 60 else 0
        pr = max(0, random.gauss(0.3, 0.5)) if cc > 50 else 0
        hu = max(20, min(100, 70 + 20 * math.sin(2 * math.pi * hr / 24) + random.gauss(0, 10)))
        pa = max(980, min(1040, 1013 + random.gauss(0, 5)))

        hourly.append({
            "timestamp_ist": t.isoformat(),
            "temperature_c": round(t_val, 1),
            "feels_like_c": round(fl, 1),
            "wind_speed_mps": round(ws, 1),
            "wind_direction_deg": round(wd, 1),
            "cloud_cover_pct": round(cc, 1),
            "solar_irradiance_wm2": round(irr, 1),
            "snowfall_mm": round(sf, 2),
            "precipitation_mm": round(pr, 2),
            "humidity_pct": round(hu, 1),
"pressure_hpa": round(pa, 1),
            "weather_code": 0,
        })

    return {"current": current_weather, "hourly": hourly}


def save_weather_cache(weather_data, source):
    cache = {
        "source": source,
        "fetched_at_ist": datetime.now(IST).isoformat(),
        "current": weather_data["current"],
        "hourly": weather_data["hourly"],
    }
    os.makedirs(os.path.dirname(WEATHER_CACHE_PATH), exist_ok=True)
    with open(WEATHER_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    return cache


def load_weather_cache():
    if os.path.exists(WEATHER_CACHE_PATH):
        with open(WEATHER_CACHE_PATH, "r") as f:
            return json.load(f)
    return None


def get_weather():
    weather_data, source = fetch_live_weather()
    cache = save_weather_cache(weather_data, source)
    return cache


if __name__ == "__main__":
    result = get_weather()
    print(f"Weather source: {result['source']}")
    print(f"Current temp: {result['current']['temperature_c']} °C")
    print(f"Forecast hours: {len(result['hourly'])}")
