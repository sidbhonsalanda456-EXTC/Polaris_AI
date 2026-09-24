import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "shared", "station_config.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def check_fault_windows(hour, config):
    alerts = []
    fault_windows = config.get("fault_windows_ist", {})

    for resource, window in fault_windows.items():
        parts = window.split("-")
        start_h = int(parts[0].split(":")[0])
        end_h = int(parts[1].split(":")[0])
        if start_h <= hour <= end_h:
            alerts.append({
                "risk_level": "MEDIUM",
                "affected_resource": resource.replace("_unavailable", "").replace("_", " ").title(),
                "explanation": f"{resource.replace('_', ' ').title()} is not available during {window} IST (scheduled maintenance window).",
                "confidence_pct": 100,
                "expected_window": f"{window} IST",
            })
    return alerts


def check_disaster_windows(hour, config):
    alerts = []
    disasters = config.get("disaster_windows_ist", {})

    for disaster_name, info in disasters.items():
        window = info["time"]
        parts = window.split("-")
        start_h = int(parts[0].split(":")[0])
        end_h = int(parts[1].split(":")[0])
        if start_h <= hour <= end_h:
            affected = []
            if "hydropower_derate_percent" in info:
                affected.append("Hydropower")
            if "marine_derate_percent" in info:
                affected.append("Marine Energy")
            if "wind_derate_percent" in info:
                affected.append("Wind")
            if "solar_derate_percent" in info:
                affected.append("Solar PV")

            alerts.append({
                "risk_level": "CRITICAL",
                "affected_resource": " and ".join(affected) if affected else disaster_name.title(),
                "explanation": f"{disaster_name.title()} forecast. Resources affected: {', '.join(affected)}.",
                "confidence_pct": 85,
                "expected_window": f"{window} IST",
            })
    return alerts


def check_weather_risks(weather_data, config):
    alerts = []
    temp = weather_data.get("temperature_c", 0)
    wind_speed = weather_data.get("wind_speed_mps", 0)
    cloud_cover = weather_data.get("cloud_cover_pct", 0)
    irradiance = weather_data.get("solar_irradiance_wm2", 0)
    snowfall = weather_data.get("snowfall_mm", 0)
    ts = weather_data.get("timestamp_ist", datetime.now(IST).isoformat())

    if cloud_cover > 80:
        alerts.append({
            "risk_level": "MEDIUM",
            "affected_resource": "Solar PV",
            "explanation": f"High cloud cover ({cloud_cover}%) will significantly reduce solar generation.",
            "confidence_pct": 90,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    if irradiance < 100 and 8 <= datetime.fromisoformat(ts).hour <= 16:
        alerts.append({
            "risk_level": "MEDIUM",
            "affected_resource": "Solar PV",
            "explanation": f"Low solar irradiance ({irradiance} W/m2) during active hours reduces solar output.",
            "confidence_pct": 85,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    if wind_speed < 3:
        alerts.append({
            "risk_level": "HIGH",
            "affected_resource": "Wind",
            "explanation": f"Wind speed ({wind_speed} m/s) below cut-in speed (3 m/s). Wind turbines will not generate power.",
            "confidence_pct": 95,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    if wind_speed > 25:
        alerts.append({
            "risk_level": "CRITICAL",
            "affected_resource": "Wind",
            "explanation": f"Extreme wind speed ({wind_speed} m/s) above cut-out (25 m/s). Wind turbines shut down for safety.",
            "confidence_pct": 98,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    if snowfall > 2:
        alerts.append({
            "risk_level": "HIGH",
            "affected_resource": "Solar PV",
            "explanation": f"Heavy snowfall ({snowfall} mm) may cover solar panels and reduce output.",
            "confidence_pct": 80,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    if temp < -30:
        alerts.append({
            "risk_level": "HIGH",
            "affected_resource": "Station Demand",
            "explanation": f"Extreme cold ({temp} C) will significantly increase heating demand.",
            "confidence_pct": 88,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })

    return alerts


def check_low_renewable_alert(predicted_solar, predicted_wind, predicted_demand, ts):
    alerts = []
    total_renewable = predicted_solar + predicted_wind

    if predicted_demand > 0 and total_renewable / predicted_demand < 0.5:
        alerts.append({
            "risk_level": "HIGH",
            "affected_resource": "Station Demand",
            "explanation": f"Low predicted renewable generation ({total_renewable:.1f} kW) vs demand ({predicted_demand:.1f} kW). Deficit may require backup sources.",
            "confidence_pct": 75,
            "expected_window": f"{ts}",
            "timestamp_ist": ts,
        })
    return alerts


def generate_all_alerts(weather_data, predicted_solar=0, predicted_wind=0, predicted_demand=100):
    config = load_config()
    hour = datetime.fromisoformat(weather_data.get("timestamp_ist", datetime.now(IST).isoformat())).hour

    alerts = []
    alerts.extend(check_fault_windows(hour, config))
    alerts.extend(check_disaster_windows(hour, config))
    alerts.extend(check_weather_risks(weather_data, config))
    alerts.extend(check_low_renewable_alert(predicted_solar, predicted_wind, predicted_demand, weather_data.get("timestamp_ist", "")))

    level_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    alerts.sort(key=lambda a: level_order.get(a["risk_level"], 99))

    return alerts


if __name__ == "__main__":
    test_weather = {
        "timestamp_ist": datetime.now(IST).isoformat(),
        "temperature_c": -35,
        "wind_speed_mps": 2,
        "cloud_cover_pct": 85,
        "solar_irradiance_wm2": 50,
        "snowfall_mm": 5,
    }
    alerts = generate_all_alerts(test_weather, 10, 0, 100)
    for a in alerts:
        print(f"[{a['risk_level']}] {a['affected_resource']}: {a['explanation']}")
