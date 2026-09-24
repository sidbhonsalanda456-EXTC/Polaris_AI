import csv
import os

from forecast_24h import print_forecast, realtime_start_ist
from optimizer_lp import print_lp_results, summarize_lp, print_optimal_decision, print_legend
from resources import print_resource_inventory
from api import run_station_optimization, default_components, component_snapshot

CSV_COLUMNS = [
    "time_ist", "solar_kw", "wind_kw", "hydro_kw", "other_renew_kw",
    "battery_discharge_kw", "battery_charge_kw", "battery_state",
    "generator_kw", "hydrogen_kw", "served_kw", "critical_met",
    "battery_soc_pct", "precharge", "disaster", "event",
]


def save_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in results:
            other = (r["geothermal_used_kw"] + r["marine_used_kw"]
                     + r["biomass_used_kw"] + r["solar_thermal_used_kw"])
            w.writerow([
                r["ts_readable"], r["solar_used_kw"], r["wind_used_kw"],
                r["hydro_used_kw"], other,
                r["battery_discharge_kw"], r["battery_charge_kw"],
                r["battery_state"], r["generator_output_kw"],
                r["hydrogen_used_kw"], r["load_served_kw"],
                "Y" if r["critical_load_met"] else "N",
                r["battery_soc_after_pct"],
                "Y" if r.get("precharge_flag") else "N",
                r.get("disaster", "NONE"), r.get("event", ""),
            ])


def run_interval(interval, label, engine="lp", part=1):
    print("=" * 66)
    print(f"PART {part}/3 - 24-HOUR {label.upper()} REAL-TIME READINGS "
          f"[engine: {engine.upper()}]")
    print(f"Simulation starts NOW in real time (IST): "
          f"{realtime_start_ist().strftime('%Y-%m-%d %H:%M:%S')}")
    print("AUTO MODE: source availability (Y/N) is detected automatically; the AI")
    print("shifts to the best available source and PRE-CHARGES the battery before")
    print("predicted failures or floods/storms/tsunamis - no manual selection needed")
    print("=" * 66)

    battery, loads, generator = default_components()

    initial = component_snapshot(battery, loads, generator)
    print(f"\nINITIAL STATE:")
    print(f"  Battery:   SOC={initial['battery']['soc_percent']}% | "
          f"SOH={initial['battery']['soh_percent']}% | "
          f"Stored={initial['battery']['stored_energy_kwh']} kWh | "
          f"Capacity={initial['battery']['capacity_kwh']} kWh")
    print(f"  Loads:     {loads}")
    print(f"  Generator: Min={generator.min_kw} kW  Max={generator.max_kw} kW")

    if interval == "minute":
        print("\n[working] computing 1,440 per-minute LP readings... (~20 s)")
    elif interval == "second":
        print("\n[working] computing 86,400 per-second fast readings... (~5 s)")

    payload = run_station_optimization(interval=interval, scenario="auto",
                                       battery=battery, loads=loads,
                                       generator=generator,
                                       save_json=(interval != "second"),
                                       schedule_loads=True, engine=engine)
    forecast = payload["forecast"]
    results = payload["optimization_results"]
    show_limit = None if interval == "hourly" else 5

    print(f"\n--- 24-HOUR SOURCE & DEMAND FORECAST ({len(forecast)} readings) ---")
    print_forecast(forecast, show_limit)

    if interval == "hourly" and payload.get("deferrable_scheduled_timestamps"):
        print(f"\nLOAD SCHEDULING: WaterHeating (20 kW, deferrable) scheduled at "
              f"{len(payload['deferrable_scheduled_timestamps'])} surplus-hours")
        print(f"  -> {payload['deferrable_scheduled_timestamps'][0]} ... "
              f"{payload['deferrable_scheduled_timestamps'][-1]}")

    print(f"\n--- 24-HOUR OPTIMIZATION ({len(results)} readings) ---")
    print_lp_results(results, show_limit)
    if show_limit:
        print("  ...")
        print(f"  (showing first {show_limit} real-time rows from the top)")
        print_lp_results(results[-3:])
        print("  (last 3 real-time rows - full data in CSV)")
    summarize_lp(results, generator)
    print_optimal_decision(results, battery, sensor_row=results[-1])
    print_legend()

    emergency = payload.get("emergency", {})
    print("\n" + "=" * 66)
    print("EMERGENCY ENERGY SYSTEM - NOTIFICATIONS")
    print("=" * 66)
    alerts = emergency.get("alerts", [])
    if not alerts:
        print("  All sources healthy. No emergency situations.")
    elif len(alerts) > 20:
        for a in alerts[:10]:
            print(f"  {a}")
        print(f"  ... and {len(alerts) - 13} more notifications ...")
        for a in alerts[-3:]:
            print(f"  {a}")
        print(f"  (total notifications: {len(alerts)})")
    else:
        for a in alerts:
            print(f"  {a}")
    print(f"  Total unmet energy:        {emergency.get('total_unmet_kwh', 0.0):9.2f} kWh")
    print("=" * 66)

    print(f"\nFINAL STATE:")
    print(f"  Battery:   {battery}")
    print(f"  Generator: {generator}")

    os.makedirs("output", exist_ok=True)
    csv_path = os.path.join("output", f"auto_{interval}_{engine}.csv")
    save_csv(results, csv_path)
    print(f"\nFILES SAVED (open in Excel/VSCode):")
    if interval != "second":
        print(f"  JSON: output/{os.path.basename(payload['saved_to'])} "
              f"({len(results)} rows)")
    print(f"  CSV : {csv_path} ({len(results)} real-time rows)")


def main():
    print_resource_inventory()
    print("=" * 66)
    print("POLAR STATION - FULLY AUTOMATIC ENERGY OPTIMIZATION (24 hours)")
    print("No manual choices needed: supply is forecast, failures are detected")
    print("automatically, and the best source is chosen for every reading.")
    print("  PART 1 = per-hour,  PART 2 = per-minute,  PART 3 = per-second")
    print("=" * 66)

    run_interval("hourly", "Per Hour", engine="lp", part=1)
    print("\n\n" + "=" * 66)
    print("NEXT: PER-MINUTE REAL-TIME READINGS (1,440 readings, ~20 s)")
    print("=" * 66)
    run_interval("minute", "Per Minute", engine="lp", part=2)
    print("\n\n" + "=" * 66)
    print("NEXT: PER-SECOND REAL-TIME READINGS (86,400 readings, ~5 s)")
    print("=" * 66)
    run_interval("second", "Per Second", engine="fast", part=3)
    print("\n\nALL 3 PARTS COMPLETE.")
    print("Open the CSV files in output/ to see every per-minute and per-second row.")


if __name__ == "__main__":
    main()