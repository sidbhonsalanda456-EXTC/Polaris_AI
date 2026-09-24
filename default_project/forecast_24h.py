import math
from datetime import datetime, timedelta, timezone
from resources import (extra_renewable_kw, hydro_output, geothermal_output,
                       marine_output, biomass_output, solar_thermal_output,
                       hydrogen_fc_kw, PASSIVE_SOLAR_REDUCTION)

IST = timezone(timedelta(hours=5, minutes=30))


def realtime_start_ist():
    return datetime.now(IST)


def fmt_ts_readable(dt):
    return dt.astimezone(IST).strftime("%d-%b %H:%M:%S")

INTERVAL_INFO = {
    "hourly": (24, timedelta(hours=1), 1.0),
    "minute": (24 * 60, timedelta(minutes=1), 1.0 / 60.0),
    "second": (24 * 60 * 60, timedelta(seconds=1), 1.0 / 3600.0),
}


def solar_output(hour, solar_capacity_kw=300):
    h = int(hour)
    if h < 8 or h > 16:
        return 0.0
    if h == 8 or h == 16:
        return solar_capacity_kw * 0.15
    if h == 9 or h == 15:
        return solar_capacity_kw * 0.45
    if h == 10 or h == 14:
        return solar_capacity_kw * 0.70
    if h == 11 or h == 13:
        return solar_capacity_kw * 0.85
    return solar_capacity_kw * 0.95


def wind_speed(hour, base=6, amplitude=4):
    speed = base + amplitude * math.sin(2 * math.pi * (hour - 3) / 24)
    return max(0, speed)


def wind_power(speed, cut_in=3, rated=12, cut_out=25, capacity_kw=300):
    if speed < cut_in or speed > cut_out:
        return 0.0
    if speed >= rated:
        return capacity_kw
    return capacity_kw * (speed - cut_in) / (rated - cut_in)


def demand(hour, base=100):
    factors = {
        0: 0.80, 1: 0.75, 2: 0.75, 3: 0.75, 4: 0.75, 5: 0.80,
        6: 0.90, 7: 0.95, 8: 1.00, 9: 1.10, 10: 1.15, 11: 1.15,
        12: 1.10, 13: 1.10, 14: 1.05, 15: 1.00, 16: 1.05, 17: 1.15,
        18: 1.20, 19: 1.15, 20: 1.05, 21: 0.95, 22: 0.85, 23: 0.80,
    }
    return base * factors.get(int(hour), 1.0) * (1 - PASSIVE_SOLAR_REDUCTION)


def scenario_statuses(scenario):
    if scenario == "solar_failure":
        return "UNAVAILABLE", "AVAILABLE", "AVAILABLE", "AVAILABLE"
    if scenario == "wind_failure":
        return "AVAILABLE", "UNAVAILABLE", "AVAILABLE", "AVAILABLE"
    if scenario == "both_failure":
        return "UNAVAILABLE", "UNAVAILABLE", "AVAILABLE", "AVAILABLE"
    if scenario == "generator_failure":
        return "AVAILABLE", "AVAILABLE", "AVAILABLE", "UNAVAILABLE"
    return "AVAILABLE", "AVAILABLE", "AVAILABLE", "AVAILABLE"


def auto_statuses(hour):
    solar = "AVAILABLE"
    wind = "AVAILABLE"
    hydro = "AVAILABLE"
    generator = "AVAILABLE"

    if 2.0 <= hour < 4.0:
        wind = "UNAVAILABLE"
    if 5.0 <= hour < 6.0:
        hydro = "UNAVAILABLE"
    if 21.0 <= hour < 23.0:
        generator = "UNAVAILABLE"

    return solar, wind, hydro, generator


def disaster_at(hour):
    if 4.0 <= hour < 5.0:
        return "FLOOD"
    if 8.0 <= hour < 9.0:
        return "TSUNAMI"
    if 15.0 <= hour < 16.0:
        return "STORM"
    return "NONE"


def prod_avail(status, kw):
    if status != "AVAILABLE":
        return "not available"
    return "available" if kw > 0.01 else "not available"


DISASTER_NOTES = {
    "FLOOD": "hydro derated to 10% (silt/debris)",
    "TSUNAMI": "marine off + wind derated to 15% (coastal waves)",
    "STORM": "wind pitched to 15% + solar cut to 40% (cloud cover)",
}


def print_disaster_summary(forecast):
    by_type = {}
    for r in forecast:
        d = r.get("disaster")
        if d not in ("NONE", "", None):
            by_type.setdefault(d, []).append(r["ts_readable"])
    print("\nDISASTER FORECAST:")
    if not by_type:
        print("  none predicted in the next 24 h")
        return
    for d in sorted(by_type):
        times = by_type[d]
        print(f"  {d:8} at {times[0]} to {times[-1]}")
        print(f"           impact: {DISASTER_NOTES.get(d, '')}")
        print(f"           action: AI pre-charges battery + holds reserve for this window")


def generate_24h_forecast(start_date=None, interval="hourly",
                          solar_capacity_kw=300, wind_capacity_kw=300,
                          base_demand=100, scenario="auto"):
    if start_date is None:
        start = datetime.now(IST)
    elif start_date == "now":
        start = datetime.now(IST)
    else:
        start = datetime.fromisoformat(start_date)
    steps, delta, dt_hours = INTERVAL_INFO[interval]

    forecast = []
    for i in range(steps):
        ts = start + delta * i
        fh = ts.hour + ts.minute / 60 + ts.second / 3600

        if scenario == "auto":
            solar_status, wind_status, hydro_status, generator_status = auto_statuses(fh)
        else:
            solar_status, wind_status, hydro_status, generator_status = scenario_statuses(scenario)
        disaster = disaster_at(fh)

        sol = 0.0 if solar_status == "UNAVAILABLE" else solar_output(fh, solar_capacity_kw)
        wspd = wind_speed(fh)
        wpow = 0.0 if wind_status == "UNAVAILABLE" else wind_power(wspd, capacity_kw=wind_capacity_kw)
        hyd = hydro_output(fh) if hydro_status == "AVAILABLE" else 0.0
        geo = geothermal_output(fh)
        mar = marine_output(fh)
        bio = biomass_output(fh)
        sterm = solar_thermal_output(fh)
        h2fc = hydrogen_fc_kw(fh)
        extra = extra_renewable_kw(fh)

        if disaster == "FLOOD":
            hyd *= 0.10
        elif disaster == "STORM":
            wpow *= 0.15
            sol *= 0.40
        elif disaster == "TSUNAMI":
            mar *= 0.0
            wpow *= 0.15

        dem = demand(fh, base_demand)
        renewable = sol + wpow + hyd + geo + mar + bio + sterm + extra
        deficit = max(0, dem - renewable)
        surplus = max(0, renewable - dem)

        forecast.append({
            "timestamp": ts.isoformat(timespec="seconds"),
            "ts_readable": fmt_ts_readable(ts),
            "hour": round(fh, 2),
            "step_hours": dt_hours,
            "solar_kw": round(sol, 2),
            "wind_speed_mps": round(wspd, 2),
            "wind_kw": round(wpow, 2),
            "hydro_kw": round(hyd, 2),
            "geothermal_kw": round(geo, 2),
            "marine_kw": round(mar, 2),
            "biomass_kw": round(bio, 2),
            "solar_thermal_kw": round(sterm, 2),
            "hydrogen_fc_kw": round(h2fc, 2),
            "chp_kw": round(60.0, 2),
            "extra_renewable_kw": round(extra, 2),
            "demand_kw": round(dem, 2),
            "renewable_kw": round(renewable, 2),
            "deficit_kw": round(deficit, 2),
            "surplus_kw": round(surplus, 2),
            "solar_status": solar_status,
            "wind_status": wind_status,
            "hydro_status": hydro_status,
            "generator_status": generator_status,
            "solar_avail": prod_avail(solar_status, sol),
            "wind_avail": prod_avail(wind_status, wpow),
            "hydro_avail": prod_avail(hydro_status, hyd),
            "disaster": disaster,
        })
    return forecast


def print_forecast(forecast, show_limit=None):
    header = (f"{'Time (IST)':>16} | {'Solar':>13} | {'Wind':>13} | {'Hydro':>13} | "
              f"{'Solar(kW)':>9} | {'Wind(kW)':>8} | {'Hydro(kW)':>9} | "
              f"{'Geo(kW)':>7} | {'Mar(kW)':>7} | {'Bio(kW)':>7} | {'ST(kW)':>6} | "
              f"{'Demand(kW)':>10} | {'Def(kW)':>7} | {'Sur(kW)':>7}")
    print(header)
    print("-" * len(header))
    shown = 0
    for r in forecast:
        if show_limit and shown >= show_limit:
            print(f"  ... ({len(forecast) - shown} more rows)")
            break
        print(f"{r['ts_readable']:>16} | "
              f"{r['solar_avail']:>13} | "
              f"{r['wind_avail']:>13} | "
              f"{r['hydro_avail']:>13} | "
              f"{r['solar_kw']:>9.1f} | {r['wind_kw']:>8.1f} | "
              f"{r['hydro_kw']:>9.1f} | {r['geothermal_kw']:>7.1f} | "
              f"{r['marine_kw']:>7.1f} | {r['biomass_kw']:>7.1f} | "
              f"{r['solar_thermal_kw']:>6.1f} | {r['demand_kw']:>10.1f} | "
              f"{r['deficit_kw']:>7.1f} | {r['surplus_kw']:>7.1f}")
        shown += 1
    print_disaster_summary(forecast)