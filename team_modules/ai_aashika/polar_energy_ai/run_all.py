import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

W = 78  # master banner width


def header(title):
    print("\n" + "=" * W)
    print(f"  {title}")
    print("=" * W)


def table(rows, widths, alignment=None):
    """Perfectly aligned text table.
    rows: list of list[str] (first row = header).
    widths: list of int column widths.
    alignment: None or list; '<'/'^'/'>' per column (default '<').
    """
    if alignment is None:
        alignment = ["<"] * len(widths)
    header_row = rows[0]
    body = rows[1:]
    line = "  " + "  ".join("=" * w for w in widths) + "  "
    print(line)
    print("  " + "  ".join(
        f"{cell:{alignment[i]}{widths[i]}}" for i, cell in enumerate(header_row)
    ))
    print(line)
    for r in body:
        print("  " + "  ".join(
            f"{cell:{alignment[i]}{widths[i]}}" for i, cell in enumerate(r)
        ))
    print(line)


def main():
    now = datetime.now(IST)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")

    print("=" * W)
    print("  AI-DRIVEN SMART ENERGY MANAGEMENT SYSTEM")
    print("  POLAR RESEARCH STATION  |  AI/ML MODULE")
    print("  Team Member : Aashika     Role : AI/ML")
    print(f"  Start Time  : {stamp} IST")
    print("=" * W)

    from live_logger import LiveTelemetry
    live = LiveTelemetry(start_time=now).start()
    print(f"  LIVE TELEMETRY LOG STARTED -> capturing every passing second in "
          f"memory (stored into data/ai_telemetry_history.xlsx after analysis)")
    print(f"    Every passing second is appended LIVE from Run start ({stamp} IST).")
    print()

    # ================================================================
    # 1. STATION CONFIGURATION
    # ================================================================
    header("1. POLAR STATION CONFIGURATION")

    with open("shared/station_config.json") as f:
        config = json.load(f)

    rs = config["resources"]
    res_rows = [["Resource", "Capacity", "Unit", "Type"]]
    res_rows.append(["Solar PV", "300", "kW", "MODELED"])
    res_rows.append(["Wind", "300", "kW", "MODELED"])
    res_rows.append(["Hydropower", "200", "kW", "MODELED"])
    res_rows.append(["Geothermal", "100", "kW", "MODELED"])
    res_rows.append(["Marine Energy", "50", "kW", "MODELED"])
    res_rows.append(["Biomass / Biogas", "60", "kW", "MODELED"])
    res_rows.append(["Solar Thermal", "30", "kW", "MODELED"])
    res_rows.append(["Hydrogen Fuel Cell", "50", "kW", "MODELED"])
    res_rows.append(["Battery Storage", "2000", "kWh", "MODELED"])
    res_rows.append(["Diesel Generator", "100", "kW", "MODELED"])
    res_rows.append(["CHP / Cogeneration", "60", "kW", "MODELED"])
    res_rows.append(["Passive Solar", "10% cut", "-", "EFFICIENCY"])
    table(res_rows, [22, 10, 8, 14])

    ld = config["loads"]
    print(f"\n  LOADS:  Base Total {ld['base_total_demand_kw']} kW  |  Critical {ld['critical_total_kw']} kW  |  "
          f"Heating {ld['heating_kw']} kW  |  Communication {ld['communication_kw']} kW  |  "
          f"Medical {ld['medical_kw']} kW  |  Laboratory {ld['laboratory_kw']} kW  |  "
          f"Water Heating {ld['water_heating_kw']} kW\n")

    fw = config["fault_windows_ist"]
    dw = config["disaster_windows_ist"]
    fault_names = {"wind_unavailable": "WIND", "hydro_unavailable": "HYDRO", "diesel_unavailable": "DIESEL"}
    faults_rows = [["Maintenance", "IST Window", "", "Disaster", "IST Window"]]
    fault_list = list(fw.items())
    disaster_list = list(dw.items())
    for i in range(max(len(fault_list), len(disaster_list))):
        f_part = ("", "") if i >= len(fault_list) else (
            fault_names[fault_list[i][0]], fault_list[i][1])
        d_part = ("", "") if i >= len(disaster_list) else (
            disaster_list[i][0].upper(), disaster_list[i][1]["time"])
        faults_rows.append([f_part[0], f_part[1], "", d_part[0], d_part[1]])
    table(faults_rows, [22, 12, 12, 14, 13])
    print("  Maintenance window = scheduled upkeep time when that resource is OFF line.")
    print("  Disaster window    = forecast time when a natural event may reduce generation.")

    # ================================================================
    # 2. LIVE DATA & AI HISTORY ARCHIVE
    # ================================================================
    header("2. LIVE DATA & AI HISTORY ARCHIVE")

    from history_store import (load_history, seed_history_if_empty, history_stats)
    history, seeded = seed_history_if_empty()
    hstats = history_stats(history)

    print(f"\n  Source        : Integrated station sensor network")
    print(f"  Archive file  : data/ai_history.json")
    print(f"  Backfill      : {hstats['backfill_days']} days of recent hourly station data (first run only)")
    print(f"  Resolution    : every 1 second, every 1 minute, every 1 hour  (India Standard Time)")
    if seeded:
        print("  Status        : ARCHIVE CREATED AND SEEDED - now it only grows with live data")
    else:
        print("  Status        : ARCHIVE LOADED - new live data appended on every run")

    info_rows = [["Section", "Contents", "Readings"]]
    info_rows.append(["1. RESOURCES", "solar, wind, hydro, geo, marine, bio, ST, H2,",
                      f"{hstats['resource_rows']:,}"])
    info_rows.append(["", "battery, diesel, CHP + demand (kW / kWh)",
                      ""])
    info_rows.append(["2. WEATHER", "temperature, wind speed, cloud, irradiance,",
                      f"{hstats['weather_rows']:,}"])
    info_rows.append(["", "snowfall, humidity, pressure", ""])
    table(info_rows, [18, 52, 12])

    # Models learn from the hourly entries in the archive.
    from history_store import to_training_dataframe
    df = to_training_dataframe(history)

    w_rows = [["Parameter", "Min", "Max", "Mean"]]
    w_rows.append(["Temperature (C)", f"{df['temperature_c'].min():.1f}",
                   f"{df['temperature_c'].max():.1f}", f"{df['temperature_c'].mean():.1f}"])
    w_rows.append(["Wind Speed (m/s)", f"{df['wind_speed_mps'].min():.1f}",
                   f"{df['wind_speed_mps'].max():.1f}", f"{df['wind_speed_mps'].mean():.1f}"])
    w_rows.append(["Cloud Cover (%)", f"{df['cloud_cover_pct'].min():.1f}",
                   f"{df['cloud_cover_pct'].max():.1f}", f"{df['cloud_cover_pct'].mean():.1f}"])
    w_rows.append(["Solar Irradiance (W/m2)", f"{df['solar_irradiance_wm2'].min():.1f}",
                   f"{df['solar_irradiance_wm2'].max():.1f}", f"{df['solar_irradiance_wm2'].mean():.1f}"])
    w_rows.append(["Snowfall (mm)", f"{df['snowfall_mm'].min():.2f}",
                   f"{df['snowfall_mm'].max():.2f}", f"{df['snowfall_mm'].mean():.2f}"])
    print("\n  WEATHER STATISTICS (from AI history archive)")
    table(w_rows, [26, 10, 10, 10], ["<", ">", ">", ">"])

    e_rows = [["Parameter", "Min", "Max", "Mean"]]
    e_rows.append(["Solar (kW)", f"{df['solar_actual_kw'].min():.1f}",
                   f"{df['solar_actual_kw'].max():.1f}", f"{df['solar_actual_kw'].mean():.1f}"])
    e_rows.append(["Wind (kW)", f"{df['wind_actual_kw'].min():.1f}",
                   f"{df['wind_actual_kw'].max():.1f}", f"{df['wind_actual_kw'].mean():.1f}"])
    e_rows.append(["Demand (kW)", f"{df['demand_actual_kw'].min():.1f}",
                   f"{df['demand_actual_kw'].max():.1f}", f"{df['demand_actual_kw'].mean():.1f}"])
    print("  RESOURCE STATISTICS (from AI history archive)")
    table(e_rows, [26, 10, 10, 10], ["<", ">", ">", ">"])

    # ================================================================
    # 3. MODEL TRAINING
    # ================================================================
    header("3. AI/ML MODEL TRAINING  [Algorithm: Random Forest]")

    from preprocess import load_data, preprocess, get_feature_sets
    from solar_model import train_solar_model
    from wind_model import train_wind_model
    from demand_model import train_demand_model

    df = preprocess(df)
    solar_f, wind_f, demand_f = get_feature_sets()
    split = int(len(df) * 0.8)

    def show_model(sub_title, model, metrics, features):
        print("\n  " + "-" * (W - 4))
        print(f"  {sub_title}")
        print("  " + "-" * (W - 4))
        print(f"    Algorithm    : RandomForestRegressor (200 trees)")
        print(f"    Features     : {', '.join(features)}")
        print(f"    Train/Test   : {split:,} / {(len(df) - split):,} rows  (first 80% train, last 20% test)")
        m_rows = [["Metric", "Value", "Meaning"]]
        m_rows.append(["MAE", f"{metrics['test']['mae']:.2f} kW",
                       "average prediction error (lower is better)"])
        m_rows.append(["RMSE", f"{metrics['test']['rmse']:.2f} kW",
                       "error penalizing large mistakes (lower is better)"])
        m_rows.append(["R2 Score", f"{metrics['test']['r2']:.4f}",
                       "prediction accuracy (1.0 = perfect)"])
        print("    MODEL METRICS")
        table(m_rows, [12, 10, 50], ["<", ">", "<"])
        print("    FEATURE IMPORTANCE  (higher = more influence on the prediction)")
        fi_rows = [["Feature", "Importance"]]
        for feat, imp in sorted(metrics["feature_importance"].items(), key=lambda x: -x[1]):
            fi_rows.append([feat, f"{imp:.4f}"])
        table(fi_rows, [34, 12], ["<", ">"])
        return model

    solar_model, solar_metrics, _, _, _ = train_solar_model(df, solar_f)
    show_model("3A. SOLAR PV PREDICTION MODEL", solar_model, solar_metrics, solar_f)

    wind_model, wind_metrics, _, _, _ = train_wind_model(df, wind_f)
    show_model("3B. WIND POWER PREDICTION MODEL", wind_model, wind_metrics, wind_f)

    demand_model, demand_metrics, _, _, _ = train_demand_model(df, demand_f)
    show_model("3C. STATION DEMAND PREDICTION MODEL", demand_model, demand_metrics, demand_f)

    all_metrics = {"solar": solar_metrics, "wind": wind_metrics, "demand": demand_metrics}
    os.makedirs("output", exist_ok=True)
    with open("output/model_metrics.json", "w") as f:
        json.dump(all_metrics, f, indent=2)

    # ================================================================
    # 4. 24-HOUR FORECAST
    # ================================================================
    header("4. AI 24-HOUR WEATHER & ENERGY FORECAST")

    from weather_service import get_weather
    from predict_24h import generate_24h_forecast
    from risk_alerts import generate_all_alerts

    weather = get_weather()
    weather_source = weather.get("source", "unknown")
    source_label = {"polar_station_live_feed": "LIVE STATION SENSOR FEED",
                    "live_open_meteo": "OPEN-METEO API"}.get(weather_source, weather_source.upper())
    print(f"\n  Weather Source : {source_label}")
    print("  Weather API   : https://api.open-meteo.com/v1/forecast?latitude="
          f"{config['station']['latitude']}&longitude={config['station']['longitude']}"
          "&timezone=Asia%2FKolkata")
    print("  Note          : Polar-coordinate conditions streamed live from the station "
          "weather network.")
    if weather_source == "live_open_meteo":
        print("  Feed          : Open-Meteo API matched station coordinates.")
    else:
        print("  Feed          : Station weather network (polar-coordinate model mesh).")

    current = weather.get("current", {})
    c_rows = [["Parameter", "Value", "Unit"]]
    c_rows.append(["Temperature", f"{current.get('temperature_c', 0):.1f}", "C"])
    c_rows.append(["Feels Like", f"{current.get('feels_like_c', 0):.1f}", "C"])
    c_rows.append(["Wind Speed", f"{current.get('wind_speed_mps', 0):.1f}", "m/s"])
    c_rows.append(["Wind Direction", f"{current.get('wind_direction_deg', 0):.1f}", "deg"])
    c_rows.append(["Cloud Cover", f"{current.get('cloud_cover_pct', 0):.1f}", "%"])
    c_rows.append(["Solar Irradiance", f"{current.get('solar_irradiance_wm2', 0):.1f}", "W/m2"])
    c_rows.append(["Snowfall", f"{current.get('snowfall_mm', 0):.2f}", "mm"])
    c_rows.append(["Humidity", f"{current.get('humidity_pct', 0):.1f}", "%"])
    c_rows.append(["Pressure", f"{current.get('pressure_hpa', 0):.1f}", "hPa"])
    print("\n  CURRENT WEATHER CONDITIONS")
    table(c_rows, [22, 12, 10], ["<", ">", "<"])

    result = generate_24h_forecast(
        weather, solar_model, wind_model, demand_model,
        solar_metrics, wind_metrics, demand_metrics
    )
    forecast = result["forecast"][:24]

    # ---- 24-hour prediction table (solar / wind / demand) ----
    p_rows = [["Time (IST)", "Solar", "Wind", "Demand", "Solar", "Wind", "Demand"],
              ["", "kW", "kW", "kW", "Conf%", "Conf%", "Conf%"]]
    for f in forecast:
        ts = f["timestamp_ist"][:16].replace("T", " ")
        g = f["predicted_generation_kw"]
        c = f["model_confidence_percent"]
        p_rows.append([
            ts,
            f"{g['solar_pv']:.1f}", f"{g['wind']:.1f}", f"{f['predicted_demand_kw']:.1f}",
            f"{c['solar']:.1f}", f"{c['wind']:.1f}", f"{c['demand']:.1f}",
        ])
    print("\n  24-HOUR PREDICTED GENERATION & DEMAND (per hour)")
    table(p_rows, [19, 8, 8, 9, 8, 8, 9], ["<", ">", ">", ">", ">", ">", ">"])

    # ---- renewable resources forecast ----
    ren_rows = [["Time (IST)", "Solar", "Wind", "Hydro", "Geo", "Marine", "Bio", "ST"]]
    for f in forecast:
        ts = f["timestamp_ist"][:16].replace("T", " ")
        g = f["predicted_generation_kw"]
        ren_rows.append([
            ts,
            f"{g['solar_pv']:.1f}", f"{g['wind']:.1f}", f"{g['hydropower']:.1f}",
            f"{g['geothermal']:.1f}", f"{g['marine_energy']:.1f}",
            f"{g['biomass_biogas']:.1f}", f"{g['solar_thermal']:.1f}",
        ])
    print("\n  RENEWABLE GENERATION FORECAST (kW)")
    table(ren_rows, [19, 8, 8, 8, 7, 8, 7, 6], ["<", ">", ">", ">", ">", ">", ">", ">"])

    # ---- backup & storage forecast ----
    b_rows = [["Time (IST)", "H2 Cell", "Battery", "Diesel", "CHP"]]
    for f in forecast:
        ts = f["timestamp_ist"][:16].replace("T", " ")
        g = f["predicted_generation_kw"]
        b_rows.append([
            ts,
            f"{g['hydrogen_fuel_cell_available']:.1f}",
            f"{g['battery_available']:.1f}",
            f"{g['diesel_generator_available']:.1f}",
            f"{g['chp_available']:.1f}",
        ])
    print("\n  BACKUP & STORAGE FORECAST (kW, Battery in kWh)")
    table(b_rows, [19, 10, 10, 9, 9], ["<", ">", ">", ">", ">"])
    print("  Note: Diesel = 0.0 during scheduled maintenance (21:00-22:59 IST).")

    # ---- availability status ----
    a_rows = [["Time (IST)", "Solar", "Wind", "Hydro", "Geo", "Marine", "Bio",
               "ST", "H2", "Batt", "Diesel", "CHP"]]
    for f in forecast:
        ts = f["timestamp_ist"][:16].replace("T", " ")
        av = f["availability"]
        a_rows.append([
            ts,
            "Y" if av.get("solar_pv") == "available" else "N",
            "Y" if av.get("wind") == "available" else "N",
            "Y" if av.get("hydropower") == "available" else "N",
            "Y" if av.get("geothermal") == "available" else "N",
            "Y" if av.get("marine_energy") == "available" else "N",
            "Y" if av.get("biomass_biogas") == "available" else "N",
            "Y" if av.get("solar_thermal") == "available" else "N",
            "Y" if av.get("hydrogen_fuel_cell") == "available" else "N",
            "Y" if av.get("battery") == "available" else "N",
            "Y" if av.get("diesel_generator") == "available" else "N",
            "Y" if av.get("chp") == "available" else "N",
        ])
    print("\n  RESOURCE AVAILABILITY STATUS   (Y = available, N = not available)")
    table(a_rows, [19, 6, 6, 6, 6, 7, 6, 5, 5, 6, 7, 6], ["<"] * 12)

    # ---- recommended resource selection ----
    rec_rows = [["Time (IST)", "Demand", "1st Choice", "2nd Choice", "3rd Choice", "Status"]]
    for f in forecast:
        ts = f["timestamp_ist"][:16].replace("T", " ")
        rec = f["recommended_resources"]
        p, s, t = rec["primary"], rec["secondary"], rec["tertiary"]
        p_name = f"{p['name']} ({p['value_kw']}kW)"
        s_name = f"{s['name']} ({s['value_kw']}kW)" if s["name"] != "-" else "-"
        t_name = f"{t['name']} ({t['value_kw']}kW)" if t["name"] != "-" else "-"
        status = "DEMAND COVERED" if rec["coverage_kw"] >= f["predicted_demand_kw"] else "BACKUP NEEDED"
        rec_rows.append([ts, f"{f['predicted_demand_kw']:.1f}", p_name, s_name, t_name, status])
    print("\n  AI RECOMMENDED RESOURCE SELECTION (best-suitable mix per hour)")
    print("  Ranking logic: available renewable -> clean storage -> fossil last")
    table(rec_rows, [19, 9, 18, 18, 18, 15], ["<", ">", "<", "<", "<", "<"])

    # ================================================================
    # REAL-TIME TELEMETRY (IST) + HISTORY ARCHIVE UPDATE
    # ================================================================
    from rt_stream import build_telemetry
    import failover
    from history_store import append_rows

    sections = build_telemetry(forecast, current, start_time=now)
    live.set_context(forecast, current)
    added_w, added_r = append_rows(history, sections["weather"], sections["resources"])

    display_sections = live.snapshot_sections(sections)
    wdf = pd.DataFrame(display_sections["weather"])
    rdf = pd.DataFrame(display_sections["resources"])
    secs_w = wdf[wdf["granularity"] == "second"][-5:]
    mins_w = wdf[wdf["granularity"] == "minute"][-5:]
    secs_r = rdf[rdf["granularity"] == "second"][-5:]
    mins_r = rdf[rdf["granularity"] == "minute"][-5:]

    def pick(row, *keys):
        return [f"{row[k]:.1f}" if k != "battery_kwh" else f"{row[k]:.0f}" for k in keys]

    def w_tel_rows(sub):
        r = [["Time (IST)", "Temp(C)", "Wind(m/s)", "Cloud(%)", "Irr(W/m2)",
              "Snow(mm)", "Hum(%)", "Press(hPa)"]]
        for _, row in sub.iterrows():
            r.append([row["timestamp_ist"][:19].replace("T", " ")]
                     + pick(row, "temperature_c", "wind_speed_mps", "cloud_cover_pct",
                            "solar_irradiance_wm2", "snowfall_mm", "humidity_pct", "pressure_hpa"))
        return r

    def r_tel_rows_ren(sub):
        r = [["Time (IST)", "Solar", "Wind", "Hydro", "Geo", "Marine", "Bio", "ST"]]
        for _, row in sub.iterrows():
            r.append([row["timestamp_ist"][:19].replace("T", " ")]
                     + pick(row, "solar_kw", "wind_kw", "hydropower_kw", "geothermal_kw",
                            "marine_energy_kw", "biomass_biogas_kw", "solar_thermal_kw"))
        return r

    def r_tel_rows_store(sub):
        r = [["Time (IST)", "H2(kW)", "Battery(kWh)", "Diesel(kW)", "CHP(kW)", "Demand(kW)"]]
        for _, row in sub.iterrows():
            r.append([row["timestamp_ist"][:19].replace("T", " ")]
                     + pick(row, "h2_kw", "battery_kwh", "diesel_kw", "chp_kw", "demand_kw"))
        return r

    print("\n  REAL-TIME STATION TELEMETRY (India Standard Time)")
    print("  = every passing second is captured LIVE as it happens (true IST collection time)")
    print("  = minutes = last 60 min, hours = last 24 h -> NO future timestamps")

    print("  ---- LIVE PER-SECOND  |  WEATHER (from the moment 'Run' is pressed) ----")
    table(w_tel_rows(secs_w), [23, 8, 8, 8, 9, 8, 8, 9],
          ["<", ">", ">", ">", ">", ">", ">", ">"])
    print("  ---- LIVE PER-SECOND  |  RESOURCES (from the moment 'Run' is pressed) ----")
    table(r_tel_rows_ren(secs_r), [23, 8, 8, 8, 7, 8, 7, 6],
          ["<", ">", ">", ">", ">", ">", ">", ">"])
    table(r_tel_rows_store(secs_r), [23, 8, 11, 9, 9, 9],
          ["<", ">", ">", ">", ">", ">"])

    print("  ---- LIVE PER-MINUTE  |  WEATHER (last 5 minutes) ----")
    table(w_tel_rows(mins_w), [23, 8, 8, 8, 9, 8, 8, 9],
          ["<", ">", ">", ">", ">", ">", ">", ">"])
    print("  ---- LIVE PER-MINUTE  |  RESOURCES (last 5 minutes) ----")
    table(r_tel_rows_ren(mins_r), [23, 8, 8, 8, 7, 8, 7, 6],
          ["<", ">", ">", ">", ">", ">", ">", ">"])
    table(r_tel_rows_store(mins_r), [23, 8, 11, 9, 9, 9],
          ["<", ">", ">", ">", ">", ">"])

    print(f"  LIVE PER-HOUR DATA = the last 24 completed hours (IST); "
          f"see Section 2-3 for the next-24h AI prediction")
    print(f"  HISTORY ARCHIVE UPDATED -> data/ai_history.json")
    print(f"    Section 1 (RESOURCES): +{added_r} readings this run "
          f"(now {len(history['resources']):,} total)")
    print(f"    Section 2 (WEATHER)  : +{added_w} readings this run "
          f"(now {len(history['weather']):,} total)")
    print(f"    Every new run appends every LIVE second it collected + 60 minutes "
          f"+ 24 hours (deduplicated), so the archive grows")
    print(f"  LIVE CAPTURE ACTIVE -> real per-second readings are still being "
          f"collected while the AI analysis runs; they are stored into the "
          f"single history workbook after analysis.")

    # ================================================================
    # 4B. AUTO-FAILOVER  (live switching when a resource fails)
    # ================================================================
    fo = sections.get("failover", {"failures": [], "rows": []})
    if fo["rows"]:
        fr = fo["failures"][0]
        print("\n  AUTO-FAILOVER  (live: a resource failed -> AI switches the mix automatically)")
        print(f"  FAILED RESOURCE : {fr['name']}  |  {fr['reason']}")
        print(f"  FAILURE WINDOW  : {fr['from_dt'].strftime('%Y-%m-%d %H:%M')} -> "
              f"{fr['to_dt'].strftime('%H:%M')} IST")

        def _mix(m):
            return (f"{m['primary']['name']} ({m['primary']['value_kw']}kW) | "
                    f"{m['secondary']['name']} ({m['secondary']['value_kw']}kW) | "
                    f"{m['tertiary']['name']} ({m['tertiary']['value_kw']}kW)")

        fo_rows = [["Time (IST)", "Failed", "Old 1st/2nd/3rd",
                    "Switched TO 1st/2nd/3rd", "Old Status", "New Status"]]
        for r in fo["rows"]:
            ts = r["timestamp_ist"][:16].replace("T", " ")
            fo_rows.append([ts, r["resource_name"], _mix(r["before"]),
                            _mix(r["after"]),
                            r["before"]["strategy"], r["after"]["strategy"]])
        print("  Strategy legend -> old: BEFORE the fault | new: after the AI re-ranks")
        for row in fo_rows:
            print("  " + " | ".join(str(c)[:58] for c in row))
        print("  NOTE: predicted hour-table above still shows the original forecast; live ")
        print("        telemetry + this failover table show the ACTUAL failure and switch.")
    else:
        print("\n  AUTO-FAILOVER  : no resource failure this run - all systems healthy.")

    fo_json = failover.to_json(fo["failures"], fo["rows"])
    with open(os.path.join(BASE_DIR, "output", "failover.json"), "w") as fh:
        json.dump(fo_json, fh, indent=2)

    # ================================================================
    # 5. RISK ALERTS & DISASTER FORECAST
    # ================================================================
    header("5. RISK ALERTS & DISASTER FORECAST")

    all_alerts = []
    for f in forecast:
        for a in f.get("risk_alerts", []):
            a["timestamp_ist"] = f["timestamp_ist"]
            all_alerts.append(a)

    al_rows = [["#", "Risk Level", "Time (IST)", "Affected Resource", "Conf."]]
    for i, a in enumerate(all_alerts, 1):
        ts = a.get("timestamp_ist", "")[:16].replace("T", " ")
        al_rows.append([
            str(i), a["risk_level"], ts,
            a["affected_resource"], f"{a['confidence_pct']:.0f}%",
        ])
    print("\n  WEATHER & DISASTER RISK ALERTS  +  LIVE RESOURCE FAILURE")
    if all_alerts:
        table(al_rows, [4, 12, 19, 24, 8], ["<", "<", "<", "<", ">"])
        for i, a in enumerate(all_alerts, 1):
            print(f"    {i:>2}. {a['explanation'][:95]}")
        if fo["rows"]:
            fr0 = fo["failures"][0]
            first_row = fo["rows"][0]
            print(f"    {len(all_alerts)+1:>2}. LIVE FAILURE: {fr0['name']} : {fr0['reason']}")
            print(f"       AUTO-FAILOVER: switched from {first_row['before']['primary']['name']} "
                  f"to {first_row['after']['primary']['name']} "
                  f"(+ {first_row['after']['secondary']['name']}) for "
                  f"{first_row['timestamp_ist'][:16].replace('T', ' ')} onwards.")
    elif fo["rows"]:
        fr0 = fo["failures"][0]
        print(f"  LIVE FAILURE: {fr0['name']} - auto-failover active "
              f"(see AUTO-FAILOVER table above).")
    else:
        print("  No active alerts. All systems operating normally.")

    # ---- AI recommended mix as a RESPONSE to each alerted hour ----
    sev = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    def _mix_name(x):
        return f"{x['name']} ({x['value_kw']}kW)" if x["name"] != "-" else "-"

    resp_rows = [["Time (IST)", "Demand", "Alert (top)", "1st Choice",
                  "2nd Choice", "3rd Choice", "Status"]]
    for f in forecast:
        f_alerts = f.get("risk_alerts", [])
        if not f_alerts:
            continue
        top = max(f_alerts, key=lambda a: sev.get(a["risk_level"], 0))
        rec = f["recommended_resources"]
        p, s, t = rec["primary"], rec["secondary"], rec["tertiary"]
        if rec["coverage_kw"] >= f["predicted_demand_kw"]:
            status = "DEMAND COVERED"
        elif rec["battery_reserve_ready"]:
            status = "USE BATTERY RESERVE"
        else:
            status = "BACKUP NEEDED"
        ts = f["timestamp_ist"][:16].replace("T", " ")
        resp_rows.append([ts, f"{f['predicted_demand_kw']:.1f}",
                          f"{top['risk_level']}: {top['affected_resource']}",
                          _mix_name(p), _mix_name(s), _mix_name(t), status])
    print("\n  AI RECOMMENDED RESOURCE SELECTION (responds to each alert above)")
    print("  Ranking logic: available renewable -> clean storage -> fossil; battery acts as reserve only.")
    if len(resp_rows) > 1:
        table(resp_rows, [19, 9, 22, 18, 18, 18, 16], ["<", ">", "<", "<", "<", "<", "<"])
    else:
        print("  No alerts to respond to - recommended mix per hour is shown in Section 4.")

    disasters = [f for f in forecast if f.get("disaster_forecast")]
    if disasters:
        d_rows = [["Disaster", "Time (IST)", "Forecasted Impact"]]
        for f in disasters:
            ts = f["timestamp_ist"][:16].replace("T", " ")
            dis = f["disaster_forecast"]
            if dis == "flood":
                impact = "Hydropower derated to 10% (silt/debris)"
            elif dis == "storm":
                impact = "Wind derated to 15%, Solar cut to 40%"
            elif dis == "tsunami":
                impact = "Marine energy OFF, Wind derated to 15%"
            else:
                impact = "Severe weather watch"
            d_rows.append([dis.upper(), ts, impact])
        print("\n  DISASTER FORECAST (next 24 hours)")
        table(d_rows, [13, 19, 55], ["<", "<", "<"])
    else:
        print("\n  DISASTER FORECAST: No disasters forecast in the next 24 hours.")

    # ================================================================
    # 6. MODEL EVALUATION
    # ================================================================
    header("6. AI MODEL EVALUATION")

    ev_rows = [["Model", "MAE (kW)", "RMSE (kW)", "R2 Score", "Verdict"]]
    for name in ["solar", "wind", "demand"]:
        m = all_metrics[name]["test"]
        r2 = m["r2"]
        verdict = ("EXCELLENT" if r2 >= 0.95 else
                   "VERY GOOD" if r2 >= 0.85 else
                   "GOOD" if r2 >= 0.70 else "ACCEPTABLE")
        ev_rows.append([name.upper(), f"{m['mae']:.2f}", f"{m['rmse']:.2f}", f"{r2:.4f}", verdict])
    table(ev_rows, [12, 11, 11, 11, 12], ["<", ">", ">", ">", "<"])
    print("  METRIC EXPLANATIONS (what the numbers mean):")
    print("    MAE  = Mean Absolute Error -> average prediction error in kW. Lower is better.")
    print("    RMSE = Root Mean Squared Error -> error that heavily penalizes large mistakes. Lower is better.")
    print("    R2   = R-squared Score -> how closely predictions match actual values.")
    print("           1.0 = perfect, 0.7+ = good, 0 = model is just guessing.")

    # ================================================================
    # 7. CHART GENERATION
    # ================================================================
    header("7. CHART GENERATION")

    from visualization import generate_all_charts

    solar_pred_test = np.clip(solar_model.predict(df[solar_f].values[split:]), 0, 300)
    wind_pred_test = np.clip(wind_model.predict(df[wind_f].values[split:]), 0, 300)
    demand_pred_test = np.clip(demand_model.predict(df[demand_f].values[split:]), 20, 200)

    charts = generate_all_charts(
        df, all_metrics, result["forecast"],
        df["solar_actual_kw"].values[split:], solar_pred_test,
        df["wind_actual_kw"].values[split:], wind_pred_test,
        df["demand_actual_kw"].values[split:], demand_pred_test
    )

    chart_names = [
        "weather_analysis", "solar_prediction", "wind_prediction",
        "demand_prediction", "weather_impact", "resource_capacity",
        "renewable_vs_demand", "model_metrics", "feature_importance", "risk_timeline",
    ]
    ch_rows = [["#", "Chart", "Status"]]
    for i, name in enumerate(chart_names, 1):
        found = charts.get(name, "")
        status = "GENERATED" if found else "MISSING"
        ch_rows.append([str(i), f"{name}.png", status])
    table(ch_rows, [4, 34, 12], ["<", "<", "<"])
    print("  Charts saved to: output/charts/")

    # ================================================================
    # 8. TEST RESULTS
    # ================================================================
    header("8. TEST RESULTS")

    from test_project import run_test_suite
    results, passed, failed = run_test_suite()

    t_rows = [["#", "Test", "Result"]]
    for i, (name, status, msg) in enumerate(results, 1):
        t_rows.append([str(i), name, "PASS" if status == "PASS" else status])
    table(t_rows, [4, 52, 8], ["<", "<", "<"])
    if failed == 0:
        final = f"ALL {passed} TESTS PASSED"
    else:
        final = f"{passed} PASSED / {failed} FAILED"
    print(f"  Result : {passed} passed, {failed} failed   ->   {final}")

    # ================================================================
    # 8A. FINAL LIVE CAPTURE  (real per-second readings collected during the run)
    # ================================================================
    live.capture()
    live.inject_seconds(sections)

    from telemetry_history import append_history
    hist_tel = append_history(sections)
    print(f"  HISTORY WORKBOOK UPDATED   -> data/ai_telemetry_history.xlsx (single telemetry store)")
    print(f"    Live seconds: +{hist_tel['added_second']} "
          f"(real IST capture, one per passing second "
          f"from {live.t0:%H:%M:%S} IST)")
    print(f"    Minutes/Hours: +{hist_tel['added_minute']} / "
          f"+{hist_tel['added_hour']} (last 60 min / 24 h, averaged)")
    print(f"    Stored so far : {hist_tel['total_second']:,} seconds / "
          f"{hist_tel['total_minute']:,} minutes / "
          f"{hist_tel['total_hour']:,} hours")
    print(f"    Past history : {hist_tel['seed_hours']:,} real-time hours seeded "
          f"into the workbook (full backfill for the best-resource prediction model)")
    if hist_tel.get("migrated_csv"):
        print(f"    MONO-FILE MODE: data/telemetry_history.csv merged & removed - "
              f"the workbook now keeps everything")

    # ================================================================
    # 8B. HISTORY WORKBOOK (the ONE telemetry file)  - legacy excel report removed
    # ================================================================

    # ---- stop the live stream + archive this run into runs_history ----
    live_res = live.finish(sections)
    print(f"\n  LIVE TELEMETRY LOG COMPLETE -> stored into "
          f"data/ai_telemetry_history.xlsx + runs_history/")
    print(f"    Live window  : {live_res['run_start_ist']} -> {live_res['run_end_ist']} IST "
          f"({live_res['seconds']} seconds recorded in real time)")
    print(f"    RUN ARCHIVED -> {os.path.relpath(live_res['run_file'], BASE_DIR)} "
          f"(this run kept in history section: seconds + minutes + hours)")
    print(f"    Runs stored  : {live_res['run_count']} run(s) in data/runs_history/ "
          f"(see runs_summary.csv)")

    # ================================================================
    # 9. OUTPUT FILES
    # ================================================================
    header("9. OUTPUT FILES")

    f_rows = [["File", "Description"]]
    f_rows.append(["data/ai_history.json", "AI history archive (2 sections: resources + weather)"])
    f_rows.append(["data/ai_telemetry_history.xlsx",
                   "THE telemetry history file (PER SECOND / PER MINUTE / PER HOUR sheets)"])
    f_rows.append(["data/runs_history/",
                   "History data section - every pressed run stored with its own time"])
    f_rows.append(["output/failover.json", "Auto-failover log "
                   "(failed resource -> switched mix per hour)"])
    f_rows.append(["models/solar_model.pkl", "Trained solar prediction model"])
    f_rows.append(["models/wind_model.pkl", "Trained wind prediction model"])
    f_rows.append(["models/demand_model.pkl", "Trained demand prediction model"])
    f_rows.append(["output/ai_forecast.json", "24h forecast JSON for other teams"])
    f_rows.append(["output/model_metrics.json", "MAE / RMSE / R2 for all models"])
    f_rows.append(["output/charts/", "10 PNG charts"])
    table(f_rows, [38, 50], ["<", "<"])
    print("  ai_forecast.json is designed for the Energy Optimization team to read:")
    print("  weather, predicted generation, demand, availability, recommended resources, risk alerts.")

    # ================================================================
    # 10. SUMMARY
    # ================================================================
    header("10. AI/ML MODULE SUMMARY")

    print(f"\n  AI history archive            : {hstats['weather_rows']:,} weather readings\n"
          f"                                  + {hstats['resource_rows']:,} resource readings")
    print(f"  Archive growth               : +{added_w} weather, +{added_r} resource readings appended this run")
    print(f"  Real-time telemetry          : per second, per minute, per hour (IST)")
    print(f"  Models trained                : 3 (Solar PV, Wind, Station Demand)")
    print(f"  Predictions generated         : {len(result['forecast'])} hours (24h forecast)")
    print(f"  Weather data source           : {source_label}")
    print(f"  Resource alerts detected      : {len(all_alerts)}")
    print(f"  Disasters forecasted          : {len(disasters)}")
    print(f"  Resource recommendations      : AI-ranked best-suitable mix per hour")
    print(f"  Telemetry history            : {hist_tel['total_second']:,} seconds / "
          f"{hist_tel['total_minute']:,} minutes / "
          f"{hist_tel['total_hour']:,} hours (data/ai_telemetry_history.xlsx)")
    print(f"  Live telemetry stream        : {live_res['seconds']} seconds recording from Run start "
          f"({live_res['run_start_ist']} IST); archived to data/runs_history/")
    if fo_json["failures"]:
        print(f"  LIVE AUTO-FAILOVER           : {fo_json['failures'][0]['resource_name']} failed -> "
              f"switched mix for {len(fo_json['switched_hours'])} hours (see failover.json)")
    else:
        print(f"  LIVE AUTO-FAILOVER           : none (all resources healthy)")
    print(f"  Charts generated              : {len(charts)}")
    print(f"  Tests run                     : {passed} passed / {failed} failed")
    print(f"  Model accuracy (R2 score)     : Solar = {all_metrics['solar']['test']['r2']:.4f}")
    print(f"                                  Wind = {all_metrics['wind']['test']['r2']:.4f}")
    print(f"                                  Demand = {all_metrics['demand']['test']['r2']:.4f}")
    print("\n" + "=" * W)
    print("  AI/ML MODULE COMPLETE - ALL DONE!")
    print("=" * W)


if __name__ == "__main__":
    main()
