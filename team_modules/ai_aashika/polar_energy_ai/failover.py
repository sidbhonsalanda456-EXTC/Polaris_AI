import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from predict_24h import recommend_resource_mix

IST = ZoneInfo("Asia/Kolkata")

RES_NAMES = {
    "geothermal": "Geothermal", "biomass_biogas": "Biomass",
    "marine_energy": "Marine", "wind": "Wind", "hydropower": "Hydro",
    "solar_pv": "Solar PV", "solar_thermal": "Solar Thermal",
    "hydrogen_fuel_cell": "H2 Cell", "battery": "Battery",
    "chp": "CHP", "diesel_generator": "Diesel",
}

CANDIDATES = ["wind", "hydropower", "geothermal", "solar_pv", "diesel_generator",
              "marine_energy", "biomass_biogas", "chp", "hydrogen_fuel_cell",
              "solar_thermal"]


def pick_failures(forecast, now=None):
    """Deterministic live failure for the demo: one resource unexpectedly fails
    starting now for the next ~2 hours. The failing resource is always one that
    is genuinely 'available' in the forecast and actually producing, so the
    auto-failover is always demonstrable.
    Returns a list of:
      {"src_key", "name", "from_dt", "to_dt", "reason"}
    """
    if not forecast:
        return []
    if now is None:
        now = datetime.now(IST)
    from_dt = now.replace(minute=0, second=0, microsecond=0)
    to_dt = from_dt + timedelta(hours=2)
    keyed = {f["timestamp_ist"][:13]: f for f in forecast}
    from_key = from_dt.strftime("%Y-%m-%dT%H")
    to_key = to_dt.strftime("%Y-%m-%dT%H")

    start = now.hour

    def eligible(key):
        for hk in (from_key, to_key):
            f = keyed.get(hk)
            if f is None or f["availability"].get(key) != "available":
                return False
            gen = f.get("predicted_generation_kw", {})
            value = float(gen.get(key, 0) or gen.get(key + "_available", 0))
            if value <= 0:
                return False
        return True

    # We pick a resource that is genuinely PRODUCING and ideally a current
    # primary/secondary pick, so the live auto-switch is always visible.
    f0 = keyed.get(from_key, {})
    rec = f0.get("recommended_resources", {})
    top_names = [rec["primary"]["name"], rec["secondary"]["name"],
                 rec["tertiary"]["name"]]
    top_names = [n for n in top_names if n != "-"]

    ordered_candidates = [CANDIDATES[(start + i) % len(CANDIDATES)]
                          for i in range(len(CANDIDATES))]

    def eligible(key):
        for hk in (from_key, to_key):
            f = keyed.get(hk)
            if f is None or f["availability"].get(key) != "available":
                return False
            gen = f.get("predicted_generation_kw", {})
            value = float(gen.get(key, 0) or gen.get(key + "_available", 0))
            if value <= 0:
                return False
        return True

    # Pass 1: try a resource that is currently ranked (visible switch).
    # Pass 2: any producing resource (failover still demonstrable).
    for pass_no in (1, 2):
        for key in ordered_candidates:
            if not eligible(key):
                continue
            if pass_no == 1 and RES_NAMES.get(key) not in top_names:
                continue
            return [{"src_key": key, "name": RES_NAMES.get(key, key.title()),
                     "from_dt": from_dt, "to_dt": to_dt,
                     "reason": "unplanned outage (equipment fault detected)"}]
    return []


def _mix_snapshot(mix):
    return {
        "primary": dict(mix["primary"]),
        "secondary": dict(mix["secondary"]),
        "tertiary": dict(mix["tertiary"]),
        "coverage_kw": mix["coverage_kw"],
        "battery_reserve_ready": mix["battery_reserve_ready"],
        "strategy": mix["strategy"],
    }


def compute_failover(forecast, failures):
    """For every forecast hour inside a failure window, re-rank the recommended
    mix WITHOUT the failed resource (availability -> not available, output -> 0).
    Returns per-affected-hour:
      {timestamp_ist, resource, resource_name, before, after}
    """
    rows = []
    for f in forecast:
        ts = datetime.fromisoformat(f["timestamp_ist"])
        hit = [fr for fr in failures if fr["from_dt"] <= ts < fr["to_dt"]]
        if not hit:
            continue
        for fr in hit:
            entry = {
                "availability": dict(f.get("availability", {})),
                "predicted_generation_kw": dict(f.get("predicted_generation_kw", {})),
                "predicted_demand_kw": f.get("predicted_demand_kw", 0),
            }
            src = fr["src_key"]
            entry["availability"][src] = "not available"
            entry["predicted_generation_kw"][src] = 0
            if src in ("hydrogen_fuel_cell", "battery", "diesel_generator"):
                entry["predicted_generation_kw"][src + "_available"] = 0
            rows.append({
                "timestamp_ist": f["timestamp_ist"],
                "resource": src,
                "resource_name": fr["name"],
                "reason": fr["reason"],
                "before": _mix_snapshot(f.get("recommended_resources", {})),
                "after": _mix_snapshot(recommend_resource_mix(entry)),
            })
    return rows


def to_json(failures, rows):
    """Serializable summary for output/failover.json."""
    return {
        "generated_at_ist": datetime.now(IST).isoformat(),
        "failures": [{
            "resource": fr["src_key"],
            "resource_name": fr["name"],
            "from_ist": fr["from_dt"].isoformat(),
            "to_ist": fr["to_dt"].isoformat(),
            "reason": fr["reason"],
        } for fr in failures],
        "switched_hours": rows,
    }


if __name__ == "__main__":
    sample = json.load(open("output/ai_forecast.json", "r"))["forecast"]
    fails = pick_failures(sample)
    print("failures:", [(f["name"], f["from_dt"].isoformat(), f["to_dt"].isoformat()) for f in fails])
    for r in compute_failover(sample, fails):
        print(r["timestamp_ist"], "FAILED", r["resource_name"],
              "-> before:", r["before"]["primary"]["name"], "| after:",
              r["after"]["primary"]["name"], r["after"]["secondary"]["name"], r["after"]["tertiary"]["name"],
              "|", r["after"]["strategy"])