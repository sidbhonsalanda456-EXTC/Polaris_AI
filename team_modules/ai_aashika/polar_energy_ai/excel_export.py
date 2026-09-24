import os
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
SUB_FONT = Font(italic=True, size=9, color="595959")
THIN = PatternFill("solid", fgColor="D9E1F2")


def _setup(ws, title, subtitle=None):
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = TITLE_FONT
    ws.cell(2, 1, subtitle if subtitle else "")
    ws.cell(2, 1).font = SUB_FONT


def write_table(ws, start_row, headers, rows, widths=None):
    """Bold header row + data rows with a light band on the header."""
    for c, h in enumerate(headers, 1):
        cell = ws.cell(start_row, c, h)
        cell.font = HDR_FONT
        cell.fill = HDR_FILL
        cell.alignment = Alignment(horizontal="center")
    for r, row in enumerate(rows, start_row + 1):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(start_row + 1, 1).coordinate
    return start_row + 1 + len(rows)


def write_kv(ws, start_row, pairs, widths=(34, 60)):
    for i, (k, v) in enumerate(pairs):
        ws.cell(start_row + i, 1, k).font = Font(bold=True)
        ws.cell(start_row + i, 2, v)
    ws.column_dimensions["A"].width = widths[0]
    ws.column_dimensions["B"].width = widths[1]
    return start_row + len(pairs)


def ts_display(ts, minutes=True):
    keep = 16 if minutes else 19
    return ts[:keep].replace("T", " ")


def overview_sheet(ws, ctx):
    _setup(ws, "OVERVIEW - AI/ML MODULE REPORT",
           "Station : McMurdo Polar Research Station (SIH260061) | AI/ML Team : Aashika")

    rows = [
        ("Generated at (IST)", ctx["run_time_ist"]),
        ("Forecast window", f"next 24 hours, starting from run time (per hour)"),
        ("Weather source", {"polar_station_live_feed": "Live station sensor feed",
                         "live_open_meteo": "Open-Meteo API"}.get(ctx["weather_source"], ctx["weather_source"])),
        ("Open-Meteo API link",
         "https://api.open-meteo.com/v1/forecast?latitude="
         f"{ctx['config']['station']['latitude']}&longitude={ctx['config']['station']['longitude']}"
         "&timezone=Asia%2FKolkata"),
        ("AI history archive", f"{ctx['hist_res']:,} resource + {ctx['hist_wth']:,} weather readings "
                               f"(before this run); +{ctx['added_r']} / +{ctx['added_w']} appended this run"),
        ("Model R2 (test)", f"Solar {ctx['metrics']['solar']['test']['r2']:.4f} | "
                            f"Wind {ctx['metrics']['wind']['test']['r2']:.4f} | "
                            f"Demand {ctx['metrics']['demand']['test']['r2']:.4f}"),
        ("Tests", f"{ctx['passed']} passed / {ctx['failed']} failed"),
        ("Charts", f"{ctx['charts']} PNG in output/charts/"),
        ("Note", "Polar-coordinate conditions streamed live from the station weather network."),
        ("Note", "Per-minute telemetry keeps the last 60 minutes before the run (e.g. run at 12:07 "
                 "captures 12:05, 12:06, ...). Per-second keeps the last 60 seconds."),
    ]
    write_kv(ws, 4, rows)


def current_weather_sheet(ws, ctx):
    _setup(ws, "CURRENT WEATHER CONDITIONS")
    c = ctx["current"]
    rows = [
        ["Time (IST)", ts_display(c.get("timestamp_ist", ""), False)],
        ["Temperature (C)", c.get("temperature_c", 0)],
        ["Feels Like (C)", c.get("feels_like_c", 0)],
        ["Wind Speed (m/s)", c.get("wind_speed_mps", 0)],
        ["Wind Direction (deg)", c.get("wind_direction_deg", 0)],
        ["Cloud Cover (%)", c.get("cloud_cover_pct", 0)],
        ["Solar Irradiance (W/m2)", c.get("solar_irradiance_wm2", 0)],
        ["Snowfall (mm)", c.get("snowfall_mm", 0)],
        ["Precipitation (mm)", c.get("precipitation_mm", 0)],
        ["Humidity (%)", c.get("humidity_pct", 0)],
        ["Pressure (hPa)", c.get("pressure_hpa", 1013)],
    ]
    write_table(ws, 4, ["Parameter", "Value", ""], rows, [30, 18, 10])


def hourly_gen_demand_sheet(ws, ctx):
    _setup(ws, "24-HOUR PREDICTED GENERATION & DEMAND (per hour)",
           "Starts from run time - one row per hour for the next 24 hours (IST).")
    headers = ["Time (IST)", "Solar (kW)", "Wind (kW)", "Demand (kW)",
               "Solar Conf%", "Wind Conf%", "Demand Conf%"]
    rows = []
    for f in ctx["forecast"]:
        g = f["predicted_generation_kw"]
        c = f["model_confidence_percent"]
        rows.append([ts_display(f["timestamp_ist"]), g["solar_pv"], g["wind"],
                     f["predicted_demand_kw"], c["solar"], c["wind"], c["demand"]])
    write_table(ws, 4, headers, rows, [19, 10, 10, 11, 11, 11, 12])


def renewable_sheet(ws, ctx):
    _setup(ws, "RENEWABLE GENERATION FORECAST (per hour, kW)")
    headers = ["Time (IST)", "Solar", "Wind", "Hydro", "Geo", "Marine", "Bio", "ST"]
    rows = []
    for f in ctx["forecast"]:
        g = f["predicted_generation_kw"]
        rows.append([ts_display(f["timestamp_ist"]), g["solar_pv"], g["wind"], g["hydropower"],
                     g["geothermal"], g["marine_energy"], g["biomass_biogas"], g["solar_thermal"]])
    write_table(ws, 4, headers, rows, [19, 9, 9, 9, 9, 9, 9, 8])


def backup_sheet(ws, ctx):
    _setup(ws, "BACKUP & STORAGE FORECAST (per hour)",
           "Battery in kWh; diesel = 0.0 during scheduled maintenance (21:00-22:59 IST).")
    headers = ["Time (IST)", "H2 Cell (kW)", "Battery (kWh)", "Diesel (kW)", "CHP (kW)"]
    rows = []
    for f in ctx["forecast"]:
        g = f["predicted_generation_kw"]
        rows.append([ts_display(f["timestamp_ist"]), g["hydrogen_fuel_cell_available"],
                     g["battery_available"], g["diesel_generator_available"], g["chp_available"]])
    write_table(ws, 4, headers, rows, [19, 13, 14, 12, 10])


def availability_sheet(ws, ctx):
    _setup(ws, "RESOURCE AVAILABILITY STATUS (Y = available, N = not available, per hour)")
    headers = ["Time (IST)", "Solar", "Wind", "Hydro", "Geo", "Marine", "Bio",
               "ST", "H2", "Batt", "Diesel", "CHP"]
    keys = ["solar_pv", "wind", "hydropower", "geothermal", "marine_energy", "biomass_biogas",
            "solar_thermal", "hydrogen_fuel_cell", "battery", "diesel_generator", "chp"]
    rows = []
    for f in ctx["forecast"]:
        av = f["availability"]
        rows.append([ts_display(f["timestamp_ist"])] +
                    ["Y" if av.get(k) == "available" else "N" for k in keys])
    write_table(ws, 4, headers, rows, [19] + [7] * 11)


def recommended_sheet(ws, ctx):
    _setup(ws, "AI RECOMMENDED RESOURCE SELECTION (best-suitable mix, per hour)",
           "Ranking logic: available renewable -> clean storage -> fossil last.")
    headers = ["Time (IST)", "Demand (kW)", "1st Choice", "2nd Choice", "3rd Choice",
               "Status", "Coverage (kW)", "Strategy"]
    rows = []
    for f in ctx["forecast"]:
        rec = f["recommended_resources"]
        ps = [rec["primary"], rec["secondary"], rec["tertiary"]]
        picks = [f"{p['name']} ({p['value_kw']}kW)" if p["name"] != "-" else "-" for p in ps]
        status = "DEMAND COVERED" if rec["coverage_kw"] >= f["predicted_demand_kw"] else "BACKUP NEEDED"
        rows.append([ts_display(f["timestamp_ist"]), f["predicted_demand_kw"],
                     picks[0], picks[1], picks[2], status, rec["coverage_kw"], rec["strategy"]])
    write_table(ws, 4, headers, rows, [19, 11, 20, 20, 20, 15, 12, 40])


def telemetry_sheet(ws, title, subtitle, rows, widths):
    _setup(ws, title, subtitle)
    headers = ["Time (IST)", "Granularity", "Temp (C)", "Feels (C)", "Wind (m/s)",
               "Wind dir (deg)", "Cloud (%)", "Irr (W/m2)", "Snow (mm)", "Hum (%)", "Press (hPa)",
               "Solar (kW)", "Wind (kW)", "Hydro (kW)", "Geo (kW)", "Marine (kW)",
               "Bio (kW)", "ST (kW)", "H2 (kW)", "Battery (kWh)", "Diesel (kW)",
               "CHP (kW)", "Demand (kW)"]
    write_table(ws, 4, headers, rows, [19, 11, 9, 9, 9, 12, 9, 10, 9, 9, 10,
                                       9, 9, 9, 8, 10, 8, 8, 8, 11, 9, 8, 9])


def telemetry_rows(ctx, granularity):
    wby = {}
    for w in ctx["telemetry"]["weather"]:
        wby[(w["granularity"], w["timestamp_ist"])] = w
    merged = []
    for r in ctx["telemetry"]["resources"]:
        if r["granularity"] != granularity:
            continue
        w = wby.get((r["granularity"], r["timestamp_ist"]), {})
        merged.append([ts_display(r["timestamp_ist"], False), granularity,
                       w.get("temperature_c", ""), w.get("feels_like_c", ""),
                       w.get("wind_speed_mps", ""), w.get("wind_direction_deg", ""),
                       w.get("cloud_cover_pct", ""), w.get("solar_irradiance_wm2", ""),
                       w.get("snowfall_mm", ""), w.get("humidity_pct", ""),
                       w.get("pressure_hpa", ""), r["solar_kw"], r["wind_kw"],
                       r["hydropower_kw"], r["geothermal_kw"], r["marine_energy_kw"],
                       r["biomass_biogas_kw"], r["solar_thermal_kw"], r["h2_kw"],
                       r["battery_kwh"], r["diesel_kw"], r["chp_kw"], r["demand_kw"]])
    return merged


def alert_response_sheet(ws, ctx):
    _setup(ws, "AI RECOMMENDED RESOURCE SELECTION - ALERT RESPONSE (per hour)",
           "Best-suitable mix chosen to respond to each hour's risk alert.")
    sev = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    rows = []
    for f in ctx["forecast"]:
        al = f.get("risk_alerts", [])
        if not al:
            continue
        top = max(al, key=lambda a: sev.get(a["risk_level"], 0))
        rec = f["recommended_resources"]
        picks = [f"{p['name']} ({p['value_kw']}kW)" if p["name"] != "-" else "-"
                 for p in [rec["primary"], rec["secondary"], rec["tertiary"]]]
        if rec["coverage_kw"] >= f["predicted_demand_kw"]:
            status = "DEMAND COVERED"
        elif rec["battery_reserve_ready"]:
            status = "USE BATTERY RESERVE"
        else:
            status = "BACKUP NEEDED"
        rows.append([ts_display(f["timestamp_ist"]), f["predicted_demand_kw"],
                     f"{top['risk_level']}: {top['affected_resource']}",
                     picks[0], picks[1], picks[2], status])
    if not rows:
        rows.append(["", "", "No alerts to respond to.", "", "", "", ""])
    write_table(ws, 4, ["Time (IST)", "Demand (kW)", "Alert (top)", "1st Choice",
                        "2nd Choice", "3rd Choice", "Status"],
                rows, [19, 11, 24, 20, 20, 20, 18])


def failover_sheet(ws, ctx):
    _setup(ws, "AUTO-FAILOVER (if a resource fails, AI switches the mix)",
           "Unplanned failure detected live -> recommended resources re-ranked automatically.")
    fo = ctx.get("failover", {"failures": [], "rows": []})
    rows = [[ts_display(r["timestamp_ist"]),
             r["resource_name"], r["reason"],
             f"{r['before']['primary']['name']} ({r['before']['primary']['value_kw']}kW)",
             f"{r['after']['primary']['name']} ({r['after']['primary']['value_kw']}kW)",
             f"{r['after']['secondary']['name']} (+{r['after']['secondary']['value_kw']}kW)",
             r["before"]["strategy"], r["after"]["strategy"]]
            for r in fo.get("rows", [])]
    if not rows:
        rows.append(["", "", "No resource failure detected this run - all systems healthy.",
                     "", "", "", "", ""])
    write_table(ws, 4, ["Time (IST)", "Failed Resource", "Reason", "Old 1st Choice",
                        "NEW 1st Choice", "NEW 2nd Choice", "Old Strategy", "New Strategy"],
                rows, [19, 16, 38, 22, 22, 22, 20, 20])


def alerts_sheet(ws, ctx):
    _setup(ws, "WEATHER & DISASTER RISK ALERTS")
    rows = []
    for i, a in enumerate(ctx["alerts"], 1):
        rows.append([i, a["risk_level"], ts_display(a.get("timestamp_ist", "")),
                     a["affected_resource"], a["confidence_pct"], a["explanation"]])
    if not rows:
        rows.append(["", "", "", "", "", "No active alerts. All systems operating normally."])
    write_table(ws, 4, ["#", "Risk Level", "Time (IST)", "Affected Resource", "Conf%", "Explanation"],
                rows, [5, 11, 19, 24, 8, 95])


def disaster_sheet(ws, ctx):
    _setup(ws, "DISASTER FORECAST (next 24 hours)")
    rows = []
    for f in ctx["forecast"]:
        if not f.get("disaster_forecast"):
            continue
        dis = f["disaster_forecast"]
        impact = {"flood": "Hydropower derated to 10% (silt/debris)",
                  "storm": "Wind derated to 15%, Solar cut to 40%",
                  "tsunami": "Marine energy OFF, Wind derated to 15%"}.get(dis,
                                                                           "Severe weather watch")
        rows.append([dis.upper(), ts_display(f["timestamp_ist"]), impact])
    if not rows:
        rows.append(["", "", "No disasters forecast in the next 24 hours."])
    write_table(ws, 4, ["Disaster", "Time (IST)", "Forecasted Impact"], rows, [13, 19, 55])


def config_sheet(ws, ctx):
    _setup(ws, "STATION CONFIGURATION (shared with Energy Optimization team)")
    cfg = ctx["config"]
    res = cfg["resources"]
    start = 4
    title_row = ws.cell(start, 1, "RESOURCES (capacity)")
    title_row.font = Font(bold=True)
    start = write_table(ws, start + 1,
                        ["Resource", "Capacity", "Unit"],
                        [[k.capitalize().replace("_", " "),
                          v.get("capacity_kw", v.get("average_kw", v.get("max_kw",
                            v.get("effective_capacity_kwh", v.get("demand_reduction_percent", ""))))),
                          "kW" if not isinstance(v.get("demand_reduction_percent"), (int, float)) or "capacity_kw" in v or "average_kw" in v else "kWh"]
                         for k, v in res.items()],
                        [32, 12, 10])
    start += 2
    ws.cell(start, 1, "LOADS")
    ws.cell(start, 1).font = Font(bold=True)
    start = write_table(ws, start + 1, ["Load", "Value", "Unit"],
                        [[k.replace("_", " ").title(), v,
                          "kWh" if "total" in k else "kW"] for k, v in cfg["loads"].items()],
                        [32, 12, 10])
    start += 2
    ws.cell(start, 1, "MAINTENANCE & DISASTER WINDOWS (IST)")
    ws.cell(start, 1).font = Font(bold=True)
    maint = cfg.get("fault_windows_ist", {})
    discn = cfg.get("disaster_windows_ist", {})
    rows = []
    for k, v in maint.items():
        name = k.replace("_unavailable", "").replace("_", " ").capitalize()
        rows.append([name, v, "-"])
    for k, v in discn.items():
        time_str = v.get("time", "-") if isinstance(v, dict) else str(v)
        rows.append([k.replace("_", " ").capitalize(), "-", time_str])
    write_table(ws, start + 1, ["Resource", "Maintenance Window", "Disaster Window"],
                rows, [20, 22, 22])


def create_excel_report(ctx):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    run_ts = ctx["run_time_ist"].replace(":", "").replace("-", "").replace("T", "_")[:15]
    path = os.path.join(OUTPUT_DIR, f"energy_report_{run_ts}.xlsx")

    def add(title, fn):
        ws = wb.create_sheet(title[:31])
        fn(ws)

    add("OVERVIEW", lambda ws: overview_sheet(ws, ctx))
    add("CURRENT WEATHER", lambda ws: current_weather_sheet(ws, ctx))
    add("24H PRED GEN & DEMAND", lambda ws: hourly_gen_demand_sheet(ws, ctx))
    add("RENEWABLE FORECAST", lambda ws: renewable_sheet(ws, ctx))
    add("BACKUP & STORAGE", lambda ws: backup_sheet(ws, ctx))
    add("AVAILABILITY", lambda ws: availability_sheet(ws, ctx))
    add("RECOMMENDED MIX", lambda ws: recommended_sheet(ws, ctx))
    add("TELEMETRY PER SECOND", lambda ws: telemetry_sheet(
        ws, "REAL-TIME AI TELEMETRY - EVERY SECOND",
        "Every passing second from the moment 'Run' is pressed (IST).",
        telemetry_rows(ctx, "second"), None))
    add("TELEMETRY PER MINUTE", lambda ws: telemetry_sheet(
        ws, "REAL-TIME AI TELEMETRY - EVERY MINUTE",
        "Last 60 minutes (IST). Run at 12:07 -> 12:05 and 12:06 are kept automatically.",
        telemetry_rows(ctx, "minute"), None))
    add("TELEMETRY PER HOUR", lambda ws: telemetry_sheet(
        ws, "REAL-TIME AI TELEMETRY - EVERY HOUR",
        "Next 24 hours (IST) - same values as the forecast sheets.",
        telemetry_rows(ctx, "hour"), None))
    add("RISK ALERTS", lambda ws: alerts_sheet(ws, ctx))
    add("ALERT RESPONSE MIX", lambda ws: alert_response_sheet(ws, ctx))
    add("AUTO FAILOVER", lambda ws: failover_sheet(ws, ctx))
    add("DISASTER FORECAST", lambda ws: disaster_sheet(ws, ctx))
    add("STATION CONFIG", lambda ws: config_sheet(ws, ctx))

    from safe_write import save_workbook
    save_workbook(wb, path)
    return path