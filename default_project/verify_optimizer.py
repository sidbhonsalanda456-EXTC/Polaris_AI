import os
import json
import tempfile

from battery import Battery
from loads import StationLoads
from generator import Generator
from api import run_station_optimization

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -> {detail}")


def battery_invariants(results, eff_capacity_kwh, start_soc):
    soc = start_soc
    bad = {"state": 0, "simult": 0, "conservation": 0, "range": 0, "example": ""}
    for r in results:
        disc_kw = r["battery_discharge_kw"]
        chg_kw = r["battery_charge_kw"]
        if r["battery_state"] not in ("CHARGING", "DISCHARGING", "IDLE"):
            bad["state"] += 1
        if disc_kw > 0.01 and chg_kw > 0.01:
            bad["simult"] += 1
        exp = soc - (disc_kw - chg_kw) * r["step_hours"] / eff_capacity_kwh * 100
        if abs(exp - r["battery_soc_after_pct"]) > 0.01 and not bad["example"]:
            bad["example"] = (f"row {r['timestamp']}: expected {exp:.3f}, "
                              f"got {r['battery_soc_after_pct']}")
        if abs(exp - r["battery_soc_after_pct"]) > 0.01:
            bad["conservation"] += 1
        if not (0 <= r["battery_soc_after_pct"] <= 100):
            bad["range"] += 1
        soc = r["battery_soc_after_pct"]
    check("battery_state valid every row", bad["state"] == 0, bad["state"])
    check("no simultaneous charge/discharge", bad["simult"] == 0, bad["simult"])
    check("SOC energy conservation every row", bad["conservation"] == 0,
          bad["example"] or bad["conservation"])
    check("SOC stays within 0..100", bad["range"] == 0, bad["range"])


def source_invariants(results):
    bad = {"solar": 0, "wind": 0, "hydro": 0, "gen_off": 0, "gen_range": 0,
           "geo": 0, "marine": 0, "biomass": 0, "stherm": 0, "h2": 0, "chp": 0}
    for r in results:
        if not (-1e-6 <= r["solar_used_kw"] <= 300 + 1e-6):
            bad["solar"] += 1
        if not (-1e-6 <= r["wind_used_kw"] <= 300 + 1e-6):
            bad["wind"] += 1
        if not (-1e-6 <= r["hydro_used_kw"] <= 200 + 1e-6):
            bad["hydro"] += 1
        if not (-1e-6 <= r["geothermal_used_kw"] <= 100 + 1e-6):
            bad["geo"] += 1
        if not (-1e-6 <= r["marine_used_kw"] <= 50 + 1e-6):
            bad["marine"] += 1
        if not (-1e-6 <= r["biomass_used_kw"] <= 60 + 1e-6):
            bad["biomass"] += 1
        if not (-1e-6 <= r["solar_thermal_used_kw"] <= 30 + 1e-6):
            bad["stherm"] += 1
        if not (-1e-6 <= r["hydrogen_used_kw"] <= 50 + 1e-6):
            bad["h2"] += 1
        if not (-1e-6 <= r["chp_used_kw"] <= 60 + 1e-6):
            bad["chp"] += 1
        if r["generator_status"] == "UNAVAILABLE" and r["generator_output_kw"] != 0:
            bad["gen_off"] += 1
        if not (0 <= r["generator_output_kw"] <= 100 + 1e-6):
            bad["gen_range"] += 1
    check("solar_used within availability", bad["solar"] == 0, bad["solar"])
    check("wind_used within availability", bad["wind"] == 0, bad["wind"])
    check("hydro_used within availability", bad["hydro"] == 0, bad["hydro"])
    check("geothermal_used within availability", bad["geo"] == 0, bad["geo"])
    check("marine_used within availability", bad["marine"] == 0, bad["marine"])
    check("biomass_used within availability", bad["biomass"] == 0, bad["biomass"])
    check("solar_thermal_used within availability", bad["stherm"] == 0, bad["stherm"])
    check("hydrogen_used within availability", bad["h2"] == 0, bad["h2"])
    check("chp_used within availability", bad["chp"] == 0, bad["chp"])
    check("generator off when UNAVAILABLE", bad["gen_off"] == 0, bad["gen_off"])
    check("generator within 0..100 kW", bad["gen_range"] == 0, bad["gen_range"])


def auto_summary_checks(payload, label):
    s = payload["summary"]
    check(f"{label}: readings count",
          s["readings"] == len(payload["optimization_results"]))
    crit_ok = s["critical_load_met"].split("/")
    check(f"{label}: ALL steps met with zero unmet",
          s["total_unmet_kWh"] == 0 and crit_ok[0] == crit_ok[1],
          s["critical_load_met"])
    check(f"{label}: surplus >= 0 (plus point)", s["surplus_renewable_kWh"] >= 0,
          s["surplus_renewable_kWh"])
    check(f"{label}: renewable share 0..200%", 0 <= s["renewable_share_percent"] <= 200,
          s["renewable_share_percent"])
    check(f"{label}: battery capacity is 2000 kWh",
          payload["initial_state"]["battery"]["capacity_kwh"] == 2000)
    check(f"{label}: auto-shift events detected", s["shift_events"] > 0,
          s["shift_events"])
    check(f"{label}: AI pre-charge steps (storm look-ahead)",
          s["ai_precharge_steps"] > 0, s["ai_precharge_steps"])
    check(f"{label}: AI pre-charge energy >= 0", s["ai_precharge_energy_kWh"] >= 0,
          s["ai_precharge_energy_kWh"])


def emergency_checks(payload, expected_shifts, label):
    alerts = payload["emergency"]["alerts"]
    j = "".join(alerts)
    check(f"emergency[{label}]: wind failure notified", "WIND source problem" in j)
    check(f"emergency[{label}]: hydro failure notified", "HYDRO source problem" in j)
    check(f"emergency[{label}]: generator failure notified", "GENERATOR source problem" in j)
    check(f"emergency[{label}]: alerts == shift events", len(alerts) == expected_shifts,
          f"{len(alerts)} vs {expected_shifts}")
    check(f"emergency[{label}]: unmet total == 0 kWh",
          payload["emergency"]["total_unmet_kwh"] == 0.0)


def solar_at_noon_checks(results, label):
    noon = [r for r in results if 11.0 <= r["hour"] < 13.0]
    ok_status = all(r["solar_status"] == "AVAILABLE" for r in noon)
    ok_output = all(r["solar_used_kw"] > 0 for r in noon)
    check(f"{label}: solar available at noon (11-13h)",
          ok_status and ok_output,
          f"{[r['solar_status'] for r in noon]}")


def main():
    print("=" * 60)
    print("POLAR ENERGY 24-HOUR OPTIMIZER - VERIFY (AUTO MODE)")
    print("=" * 60)

    print("\n--- HOURLY (LP) ---")
    b = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
    g = Generator(min_kw=20, max_kw=100)
    start_soc = b.soc_percent
    p = run_station_optimization(interval="hourly", engine="lp", battery=b,
                                 loads=StationLoads(), generator=g, save_json=False)
    check("hourly: 24 readings", len(p["optimization_results"]) == 24)
    check("hourly: step_hours == 1.0",
          all(r["step_hours"] == 1.0 for r in p["optimization_results"]))
    source_invariants(p["optimization_results"])
    battery_invariants(p["optimization_results"], b.effective_capacity_kwh, start_soc)
    auto_summary_checks(p, "hourly")
    solar_at_noon_checks(p["optimization_results"], "hourly")
    check("hourly: expected shift events = 5", p["summary"]["shift_events"] == 5,
          p["summary"]["shift_events"])
    check("hourly: AI pre-charge banked energy before storm",
          p["summary"]["ai_precharge_energy_kWh"] > 0,
          p["summary"]["ai_precharge_energy_kWh"])
    check("hourly: 3 disasters forecast (flood/storm/tsunami)",
          len({r["disaster"] for r in p["optimization_results"]
               if r["disaster"] not in ("NONE", "")}) == 3,
          {r["disaster"] for r in p["optimization_results"]
           if r["disaster"] not in ("NONE", "")})
    check("hourly: disaster warnings in emergency",
          len(p["emergency"]["disaster_warnings"]) > 0,
          len(p["emergency"]["disaster_warnings"]))
    emergency_checks(p, 5, "hourly")

    print("\n--- MINUTE (LP) ---")
    b = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
    g = Generator(min_kw=20, max_kw=100)
    start_soc = b.soc_percent
    p = run_station_optimization(interval="minute", engine="lp", battery=b,
                                 loads=StationLoads(), generator=g, save_json=False)
    check("minute: 1440 readings", len(p["optimization_results"]) == 1440)
    check("minute: step_hours == 1/60",
          all(abs(r["step_hours"] - 1 / 60) < 1e-9 for r in p["optimization_results"]))
    auto_summary_checks(p, "minute")
    solar_at_noon_checks(p["optimization_results"], "minute")
    check("minute: expected shift events = 300", p["summary"]["shift_events"] == 300,
          p["summary"]["shift_events"])
    emergency_checks(p, 300, "minute")

    print("\n--- SECOND (FAST ENGINE) ---")
    b = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
    g = Generator(min_kw=20, max_kw=100)
    start_soc = b.soc_percent
    p = run_station_optimization(interval="second", engine="fast", battery=b,
                                 loads=StationLoads(), generator=g, save_json=False)
    check("second: 86400 readings", len(p["optimization_results"]) == 86400)
    check("second: step_hours == 1/3600",
          all(abs(r["step_hours"] - 1 / 3600) < 1e-9 for r in p["optimization_results"]))
    battery_invariants(p["optimization_results"], b.effective_capacity_kwh, start_soc)
    auto_summary_checks(p, "second")

    print("\n--- JSON EXPORT ---")
    with tempfile.TemporaryDirectory() as tmp:
        b = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
        p = run_station_optimization(interval="hourly", engine="lp", battery=b,
                                     loads=StationLoads(), generator=Generator(),
                                     save_json=True,
                                     json_path=os.path.join(tmp, "auto_hourly_lp.json"))
        check("json: file created", os.path.exists(p["saved_to"]))
        with open(p["saved_to"], "r", encoding="utf-8") as f:
            d = json.load(f)
        check("json: parse + summary present", d["summary"]["readings"] == 24)

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("ALL CHECKS PASSED" if FAIL == 0 else "SOME CHECKS FAILED")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())