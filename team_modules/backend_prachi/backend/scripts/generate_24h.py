"""Generate a 24-HOUR simulation dataset at multiple granularities for the backend.

This addresses the request for 24 hours of data (not 30 days). It writes three
comma-separated files under backend/data/:

  polar_24h_1sec.csv   24h * 3600  =  86,400 rows   (raw second-level)
  polar_24h_1min.csv   24h * 60    =   1,440 rows   (minute-level)
  polar_24h_1hour.csv  24h * 1     =      24 rows   (hour-level)

All values are SYNTHETIC demonstration data with physically plausible ranges for
a polar research station (diurnal solar curve, wind variation, night demand).
The minute/hour files are derived by aggregating the second-level data so all
three are consistent with one another.
"""
import csv
import os
import random
from datetime import datetime, timedelta

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

FIELDS = [
    "timestamp", "temperature_c", "humidity_pct", "wind_speed_mps",
    "wind_direction_deg", "solar_irradiance_wm2", "solar_status",
    "wind_status", "solar_generation_kw", "wind_generation_kw",
    "energy_demand_kw", "battery_soc_pct", "generator_status"
]

HOURS = 24
START = datetime(2026, 3, 1, 0, 0, 0)


def simulate_seconds(rng: random.Random, dt: datetime) -> dict:
    hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    # Diurnal solar; zero during polar night window.
    solar_curve = 900.0 * max(0.0, 1 - ((hour - 12) / 6) ** 2)
    solar_status = "ONLINE" if rng.random() > 0.01 else "OFFLINE"
    wind_status = "ONLINE" if rng.random() > 0.01 else "OFFLINE"

    temp = max(-45, min(15, 8 - 22 * abs(1 - (hour / 24) * 2) + rng.uniform(-1.5, 1.5)))
    wind_speed = max(0.0, 11 + 6 * (rng.random() - 0.5))
    wind_dir = rng.uniform(0, 360)

    solar_gen = solar_curve / 100.0 if solar_status == "ONLINE" else 0.0
    wind_gen = wind_speed * 8.0 if wind_status == "ONLINE" else 0.0

    demand = 230 + 70 * abs(1 - (hour / 24) * 2) + rng.uniform(-8, 8)

    return {
        "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": round(temp, 2),
        "humidity_pct": round(rng.uniform(45, 88), 1),
        "wind_speed_mps": round(wind_speed, 2),
        "wind_direction_deg": round(wind_dir, 1),
        "solar_irradiance_wm2": round(solar_curve, 1),
        "solar_status": solar_status,
        "wind_status": wind_status,
        "solar_generation_kw": round(solar_gen, 4),
        "wind_generation_kw": round(wind_gen, 4),
        "energy_demand_kw": round(demand, 3),
        "battery_soc_pct": round(rng.uniform(55, 90), 1),
        "generator_status": "AVAILABLE" if rng.random() > 0.05 else "UNAVAILABLE",
    }


def aggregate(seconds: list, dt: datetime, label: str, n: int) -> dict:
    """Aggregate the 'n' second-level rows belonging to one bucket."""
    def mode(vals):
        return max(set(vals), key=vals.count)

    def avg(field):
        return round(sum(r[field] for r in seconds) / len(seconds), 2)

    solar_status = mode([r["solar_status"] for r in seconds])
    wind_status = mode([r["wind_status"] for r in seconds])
    solar_total = round(sum(r["solar_generation_kw"] for r in seconds), 4)
    wind_total = round(sum(r["wind_generation_kw"] for r in seconds), 4)
    # For energy, keep the bucket-mean as instantaneous_kw so trends are readable,
    # but also expose generated totals for the AI module.
    return {
        "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": avg("temperature_c"),
        "humidity_pct": avg("humidity_pct"),
        "wind_speed_mps": avg("wind_speed_mps"),
        "wind_direction_deg": avg("wind_direction_deg"),
        "solar_irradiance_wm2": avg("solar_irradiance_wm2"),
        "solar_status": solar_status,
        "wind_status": wind_status,
        "solar_generation_kw": round(solar_total / n, 4),
        "wind_generation_kw": round(wind_total / n, 4),
        "energy_demand_kw": avg("energy_demand_kw"),
        "battery_soc_pct": avg("battery_soc_pct"),
        "generator_status": mode([r["generator_status"] for r in seconds]),
        "n_seconds": n,
        "solar_energy_kwh": round(solar_total / 3600.0, 4),
        "wind_energy_kwh": round(wind_total / 3600.0, 4),
    }


def write(path, rows, fields=FIELDS):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):>6} rows -> {os.path.relpath(path, _BASE)}")


def main():
    rng = random.Random(7)

    # 1) Second-level for the full 24 hours.
    sec_rows = []
    cur = START
    for _ in range(HOURS * 3600):
        sec_rows.append(simulate_seconds(rng, cur))
        cur += timedelta(seconds=1)
    write(os.path.join(DATA_DIR, "polar_24h_1sec.csv"), sec_rows)

    # 2) Minute-level: 60-second buckets.
    min_rows = []
    for m in range(HOURS * 60):
        bucket = sec_rows[m * 60:(m + 1) * 60]
        min_rows.append(aggregate(bucket, START + timedelta(minutes=m), "1min", 60))
    write(os.path.join(DATA_DIR, "polar_24h_1min.csv"), min_rows,
          fields=FIELDS + ["n_seconds", "solar_energy_kwh", "wind_energy_kwh"])

    # 3) Hour-level: 3600-second buckets.
    hour_rows = []
    for h in range(HOURS):
        bucket = sec_rows[h * 3600:(h + 1) * 3600]
        hour_rows.append(aggregate(bucket, START + timedelta(hours=h), "1hour", 3600))
    write(os.path.join(DATA_DIR, "polar_24h_1hour.csv"), hour_rows,
          fields=FIELDS + ["n_seconds", "solar_energy_kwh", "wind_energy_kwh"])

    print(f"\nDone. 24 hours => 1sec ({len(sec_rows)}), 1min ({len(min_rows)}), 1hour ({len(hour_rows)})")


if __name__ == "__main__":
    main()
