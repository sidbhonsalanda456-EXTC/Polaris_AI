"""Business services: derive current energy state and relay optimizer traffic."""
from ..storage.database import Database
from ..config import get_resource_config


def current_energy(db: Database) -> dict:
    """Compute the latest energy snapshot from the most recent reading."""
    latest = db.latest(1)
    if not latest:
        return {
            "timestamp": None, "solar_generation_kw": 0.0, "wind_generation_kw": 0.0,
            "renewable_generation_kw": 0.0, "energy_demand_kw": 0.0, "deficit_kw": 0.0,
        }
    r = latest[0]
    renewable = r["solar_generation_kw"] + r["wind_generation_kw"]
    deficit = max(0.0, r["energy_demand_kw"] - renewable)
    return {
        "timestamp": r["timestamp"],
        "solar_generation_kw": r["solar_generation_kw"],
        "wind_generation_kw": r["wind_generation_kw"],
        "renewable_generation_kw": round(renewable, 3),
        "energy_demand_kw": r["energy_demand_kw"],
        "deficit_kw": round(deficit, 3),
    }


def current_battery(db: Database) -> dict:
    """Return battery status from the latest reading + static config."""
    rc = get_resource_config().get("battery", {})
    latest = db.latest(1)
    soc = latest[0]["battery_soc_pct"] if latest and latest[0].get("battery_soc_pct") is not None \
        else rc.get("soc_percent", 0)
    result = db.last_optimizer_result()
    charging = bool(result and result.get("battery_charge_kw", 0) > 0)
    return {
        "timestamp": latest[0]["timestamp"] if latest else None,
        "soc_percent": soc,
        "charging": charging,
        "capacity_kwh": rc.get("capacity_kwh", 0),
        "status": "AVAILABLE" if rc.get("enabled") else "UNAVAILABLE",
    }
