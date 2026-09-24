import json
import os
from datetime import datetime

from battery import Battery
from loads import StationLoads
from generator import Generator
from forecast_24h import generate_24h_forecast
from optimizer_lp import run_24h_lp
from scheduler import schedule_deferrable
from emergency import EmergencySystem

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def default_components():
    battery = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
    loads = StationLoads()
    generator = Generator(min_kw=20, max_kw=100)
    return battery, loads, generator


def component_snapshot(battery, loads, generator):
    return {
        "battery": {
            "capacity_kwh": battery.capacity_kwh,
            "soh_percent": battery.soh_percent,
            "effective_capacity_kwh": round(battery.effective_capacity_kwh, 2),
            "soc_percent": battery.soc_percent,
            "min_soc_percent": battery.min_soc_percent,
            "stored_energy_kwh": round(battery.stored_energy_kwh, 2),
        },
        "loads": {
            "critical_kw": loads.critical_total_kw,
            "noncritical_kw": loads.noncritical_total_kw,
            "total_kw": loads.total_demand_kw,
            "critical_loads": [l.name for l in loads.critical_loads],
            "noncritical_loads": [l.name for l in loads.noncritical_loads],
        },
        "generator": {
            "min_kw": generator.min_kw,
            "max_kw": generator.max_kw,
            "fuel_rate_l_per_kwh": generator.fuel_rate,
            "status": generator.status,
            "total_fuel_used_liters": round(generator.total_fuel_used_liters, 2),
            "total_energy_produced_kwh": round(generator.total_energy_produced_kwh, 2),
        },
    }


def compute_summary(results, generator):
    sol = sum(r["solar_used_kw"] * r["step_hours"] for r in results)
    win = sum(r["wind_used_kw"] * r["step_hours"] for r in results)
    hyd = sum(r["hydro_used_kw"] * r["step_hours"] for r in results)
    gth = sum(r["geothermal_used_kw"] * r["step_hours"] for r in results)
    mar = sum(r["marine_used_kw"] * r["step_hours"] for r in results)
    bio = sum(r["biomass_used_kw"] * r["step_hours"] for r in results)
    sth = sum(r["solar_thermal_used_kw"] * r["step_hours"] for r in results)
    h2 = sum(r["hydrogen_used_kw"] * r["step_hours"] for r in results)
    chp = sum(r["chp_used_kw"] * r["step_hours"] for r in results)
    renew = sum(r["renewable_used_kw"] * r["step_hours"] for r in results)
    battd = sum(r["battery_discharge_kw"] * r["step_hours"] for r in results)
    battc = sum(r["battery_charge_kw"] * r["step_hours"] for r in results)
    pree = sum(r.get("precharge_kw", 0) * r["step_hours"] for r in results)
    prerows = sum(1 for r in results if r.get("precharge_flag"))
    gen = sum(r["generator_output_kw"] * r["step_hours"] for r in results)
    served = sum(r["load_served_kw"] * r["step_hours"] for r in results)
    unmet = sum(r["unmet_kw"] * r.get("step_hours", 1.0) for r in results)
    crit = sum(1 for r in results if r["critical_load_met"])
    nonc = sum(1 for r in results if r["noncritical_load_met"])
    FAILURE_MARKERS = ("SOLAR FAILURE", "WIND FAILURE", "HYDRO FAILURE",
                       "GENERATOR DOWN")
    shifted = sum(1 for r in results
                  if any(m in r["event"] for m in FAILURE_MARKERS))
    idle = sum(1 for r in results if r["battery_state"] == "IDLE")
    total = len(results)
    demand_total = sum(r["demand_kw"] * r["step_hours"] for r in results)
    surplus_total = sum(max(0, r["surplus_renewable_kw"]) * r["step_hours"]
                        for r in results)
    renew_share = (renew / demand_total * 100) if demand_total else 0
    return {
        "readings": total,
        "total_solar_used_kWh": round(sol, 2),
        "total_wind_used_kWh": round(win, 2),
        "total_hydro_used_kWh": round(hyd, 2),
        "total_geothermal_used_kWh": round(gth, 2),
        "total_marine_used_kWh": round(mar, 2),
        "total_biomass_used_kWh": round(bio, 2),
        "total_solar_thermal_used_kWh": round(sth, 2),
        "total_hydrogen_used_kWh": round(h2, 2),
        "total_renewable_used_kWh": round(renew, 2),
        "total_battery_discharge_kWh": round(battd, 2),
        "total_battery_charge_kWh": round(battc, 2),
        "battery_idle_steps": idle,
        "total_generator_output_kWh": round(gen, 2),
        "total_chp_output_kWh": round(chp, 2),
        "total_energy_served_kWh": round(served, 2),
        "total_unmet_kWh": round(unmet, 2),
        "surplus_renewable_kWh": round(surplus_total, 2),
        "renewable_share_percent": round(renew_share, 2),
        "total_fuel_used_liters": round(generator.total_fuel_used_liters, 2),
        "critical_load_met": f"{crit}/{total}",
        "noncritical_load_met": f"{nonc}/{total}",
        "shift_events": shifted,
        "ai_precharge_steps": prerows,
        "ai_precharge_energy_kWh": round(pree, 2),
    }


def run_station_optimization(interval="hourly", scenario="auto",
                             battery=None, loads=None, generator=None,
                             save_json=True, json_path=None, start_date=None,
                             schedule_loads=True, deferrable_kw=None,
                             deferrable_hours=10, engine="lp"):
    battery, loads, generator = (
        battery or default_components()[0],
        loads or default_components()[1],
        generator or default_components()[2],
    )

    if deferrable_kw is None:
        deferrable_kw = loads.deferrable_total_kw

    forecast = generate_24h_forecast(interval=interval, scenario=scenario,
                                     start_date=start_date)
    scheduled_ts = []
    if schedule_loads and interval == "hourly":
        scheduled_ts = schedule_deferrable(forecast, deferrable_kw=deferrable_kw,
                                           run_hours_per_day=deferrable_hours)

    if engine == "fast":
        from optimizer_fast import run_fast
        results = run_fast(forecast, battery, loads, generator)
    else:
        results = run_24h_lp(forecast, battery, loads, generator)
    summary = compute_summary(results, generator)

    emergency = EmergencySystem()
    emergency_alerts = emergency.monitor(results, loads)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "interval": interval,
            "scenario": scenario,
            "engine": engine,
            "start_date": start_date or "now (real time, IST +05:30)",
            "load_scheduling": schedule_loads,
            "deferrable_load_kw": deferrable_kw,
        },
        "initial_state": component_snapshot(battery, loads, generator),
        "forecast": forecast,
        "optimization_results": results,
        "final_state": component_snapshot(battery, loads, generator),
        "emergency": {
            "alerts": emergency_alerts,
            "disaster_warnings": emergency.disaster_warnings,
            "total_unmet_kwh": round(emergency.total_unmet_kwh, 2),
        },
        "summary": summary,
        "deferrable_scheduled_timestamps": scheduled_ts,
    }

    if save_json:
        if json_path is None:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            json_path = os.path.join(OUTPUT_DIR, f"{scenario}_{interval}_{engine}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        payload["saved_to"] = json_path

    return payload


def main():
    import sys
    import os
    interval = sys.argv[1] if len(sys.argv) > 1 else "hourly"
    scenario = sys.argv[2] if len(sys.argv) > 2 else "normal"
    payload = run_station_optimization(interval=interval, scenario=scenario)
    print(f"Saved results to: output/{os.path.basename(payload['saved_to'])}")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()