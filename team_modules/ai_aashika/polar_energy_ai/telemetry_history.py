import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "telemetry_history.csv")
XLSX_PATH = os.path.join(BASE_DIR, "data", "ai_telemetry_history.xlsx")

WEATHER_COLS = ["temperature_c", "feels_like_c", "wind_speed_mps",
                "wind_direction_deg", "cloud_cover_pct", "solar_irradiance_wm2",
                "snowfall_mm", "precipitation_mm", "humidity_pct", "pressure_hpa"]
RESOURCE_COLS = ["solar_kw", "wind_kw", "hydropower_kw", "geothermal_kw",
                 "marine_energy_kw", "biomass_biogas_kw", "solar_thermal_kw",
                 "h2_kw", "battery_kwh", "diesel_kw", "chp_kw", "demand_kw"]
COLUMNS = ["granularity", "timestamp_ist"] + WEATHER_COLS + RESOURCE_COLS

NUMERIC_COLS = WEATHER_COLS + RESOURCE_COLS


def _merge_sections(sections):
    """Join weather + resources on (granularity, timestamp_ist) -> one row per reading."""
    w = pd.DataFrame(sections.get("weather", []))
    r = pd.DataFrame(sections.get("resources", []))
    if w.empty:
        return pd.DataFrame(columns=COLUMNS)
    if r.empty:
        w["granularity"] = w.get("granularity", "second")
        return w.reindex(columns=COLUMNS)
    m = pd.merge(w, r, on=["granularity", "timestamp_ist"], how="outer",
                 suffixes=("", ""))
    return m.reindex(columns=COLUMNS)


def _avg_seconds_by(sec_df, bucket):
    """Average of the per-second readings grouped by a timestamp bucket.
    bucket: pd.Grouper key = 'minute' or 'hour' applied on the ISO timestamps."""
    if sec_df.empty:
        return pd.DataFrame()
    df = sec_df.copy()
    ts = pd.to_datetime(df["timestamp_ist"], format="ISO8601", utc=True)
    if bucket == "minute":
        key = ts.dt.floor("min").dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%dT%H:%M")
    else:
        key = ts.dt.floor("min").dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%dT%H")
    df["_bucket"] = key
    avg = df.groupby("_bucket")[NUMERIC_COLS].mean().round(2).reset_index()
    return avg.rename(columns={"_bucket": "timestamp_ist"})


def _apply_averages(rows, sec_df, granularity, freq):
    """For min/hour rows, replace values with the average of the seconds that
    actually fall in that bucket (fall back to the generated row otherwise)."""
    out = []
    avg_by_ts = {}
    if not sec_df.empty and sec_df["granularity"].eq("second").any():
        a = _avg_seconds_by(sec_df[sec_df["granularity"] == "second"], freq)
        if not a.empty:
            avg_by_ts = {r["timestamp_ist"]: r for _, r in a.iterrows()}
    for row in rows:
        if row.get("granularity") != granularity:
            continue
        base = dict(row)
        ts = str(base["timestamp_ist"])
        ts_key = ts[:16] if freq == "minute" else ts[:13]
        avg = avg_by_ts.get(ts_key)
        if avg is not None:
            for c in NUMERIC_COLS:
                if c in avg and pd.notna(avg[c]):
                    base[c] = avg[c]
        out.append(base)
    return out


def _new_rows(sections):
    merged = _merge_sections(sections)
    if merged.empty:
        return pd.DataFrame(columns=COLUMNS), {}
    sec_df = merged[merged["granularity"] == "second"]
    sec_rows = merged[merged["granularity"] == "second"].to_dict("records")
    min_rows = _apply_averages(merged.to_dict("records"), sec_df, "minute", "minute")
    hour_rows = _apply_averages(merged.to_dict("records"), sec_df, "hour", "hour")
    rows = sec_rows + [r for r in min_rows if
                       str(r["timestamp_ist"]) not in {x["timestamp_ist"] for x in sec_rows}
                       and r] + [
        r for r in hour_rows if
        str(r["timestamp_ist"]) not in {x["timestamp_ist"] for x in min_rows}
        and r]
    if not rows:
        return pd.DataFrame(columns=COLUMNS), {}
    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    return df, {"second": len(sec_rows), "minute": len(min_rows), "hour": len(hour_rows)}


def _read_xlsx_existing():
    from openpyxl import load_workbook
    wb = load_workbook(XLSX_PATH, read_only=True, data_only=True)
    frames = []
    for title, g in (("PER SECOND", "second"), ("PER MINUTE", "minute"),
                     ("PER HOUR", "hour")):
        if title not in wb.sheetnames:
            continue
        ws = wb[title]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 4:
            continue
        headers = list(rows[2])
        for r in rows[3:]:
            if len(r) < 2 or r[1] is None:
                continue
            rec = {"granularity": g, "timestamp_ist": r[1]}
            for j, c in enumerate(headers):
                if j == 1 or c not in (WEATHER_COLS + RESOURCE_COLS):
                    continue
                if j < len(r) and r[j] is not None:
                    rec[c] = r[j]
            frames.append(rec)
    wb.close()
    df = (pd.DataFrame(frames).reindex(columns=COLUMNS) if frames
          else pd.DataFrame(columns=COLUMNS))
    return df


def _load_existing():
    """Load the accumulated history. Preference: legacy CSV if it still exists
    (migration source with the full backfilled history), then the workbook
    itself (single-file mode)."""
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            if "timestamp_ist" in df.columns and "granularity" in df.columns:
                return df.reindex(columns=COLUMNS)
        except Exception:
            return pd.DataFrame(columns=COLUMNS)
    if os.path.exists(XLSX_PATH):
        try:
            return _read_xlsx_existing()
        except Exception:
            return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)


def read_history_df():
    """Load the full accumulated history (real-time IST) as one table the
    best-resource selection model can train/verify against. Falls back to the
    past hourly archive when nothing was captured yet."""
    df = _load_existing()
    if df.empty:
        past = _build_past_hour_rows()
        if not past.empty:
            df = past.drop_duplicates(
                subset=["granularity", "timestamp_ist"], keep="first")
    return df


def _write_excel(df):
    os.makedirs(os.path.dirname(XLSX_PATH), exist_ok=True)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="1F2A44")
    header_font = Font(bold=True, color="FFFFFF")
    title_font = Font(bold=True, size=13, color="16233B")

    order = [("PER SECOND", "second"), ("PER MINUTE", "minute"), ("PER HOUR", "hour")]
    for title, g in order:
        ws = wb.create_sheet(title)
        sub = df[df["granularity"] == g].drop(columns=["granularity"])
        ws.cell(1, 1, f"AI TELEMETRY HISTORY - {title} (IST)").font = title_font
        ws.cell(2, 1, "Readings accumulate every run. Data source: live station weather network.").font = \
            Font(italic=True, size=9, color="666666")
        hdr = list(sub.columns)
        for j, c in enumerate(hdr, 1):
            cell = ws.cell(3, j, c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for i, (_, row) in enumerate(sub.iterrows(), 4):
            for j, c in enumerate(hdr, 1):
                v = row[c]
                if pd.notna(v):
                    ws.cell(i, j, v)
        ws.freeze_panes = "B4"
        for j, c in enumerate(hdr, 1):
            letter = ws.cell(3, j).column_letter
            ws.column_dimensions[letter].width = 22 if c == "timestamp_ist" \
                else min(14, max(6, len(c) + 2))
    from safe_write import save_workbook
    ok = save_workbook(wb, XLSX_PATH)
    return XLSX_PATH, ok


def _build_past_hour_rows():
    """Pull the PAST hourly history (real-time IST backfill + appended minutes/
    hours) from the AI archive and shape it as hour/minute telemetry rows, so
    the workbook always carries a complete real-time history the resource-
    selection model can be trained/verified on. Seconds are excluded here (they
    come only from the live collector)."""
    try:
        from history_store import load_history
        h = load_history()
    except Exception:
        return pd.DataFrame(columns=COLUMNS)
    wmap = {r["timestamp_ist"]: r for r in h.get("weather", [])}
    rmap = {r["timestamp_ist"]: r for r in h.get("resources", [])}
    if not wmap or not rmap:
        return pd.DataFrame(columns=COLUMNS)
    rows = []
    now_utc = pd.Timestamp(datetime.now(IST)).tz_convert("UTC")
    for ts in sorted(set(wmap) | set(rmap)):
        try:
            tsobj = pd.to_datetime(ts, format="ISO8601", utc=True)
        except Exception:
            continue
        if tsobj > now_utc:
            continue
        w = wmap.get(ts, {})
        r = rmap.get(ts, {})
        gr = w.get("granularity") or r.get("granularity") or "hour"
        if gr == "second":
            continue
        row = {"granularity": gr, "timestamp_ist": ts}
        for c in WEATHER_COLS:
            row[c] = w.get(c, r.get(c))
        for c in RESOURCE_COLS:
            row[c] = r.get(c, w.get(c))
        rows.append(row)
    df = pd.DataFrame(rows).reindex(columns=COLUMNS) if rows else \
        pd.DataFrame(columns=COLUMNS)
    return df


def append_history(sections):
    """Append this run's telemetry to the growing history (single file:
    data/ai_telemetry_history.xlsx). Seconds are stored raw; minute and hourly
    rows are averaged from the underlying seconds where available. New rows are
    added, existing ones kept, and the PAST hourly archive is always merged in
    (real-time IST) so the history is complete for resource-selection modelling.
    If the legacy telemetry_history.csv still exists it is merged in and then
    removed once the workbook has been written successfully. Returns a summary
    dict."""
    new, counts = _new_rows(sections)
    if new.empty and not os.path.exists(CSV_PATH) and not os.path.exists(XLSX_PATH):
        past = _build_past_hour_rows()
        if not past.empty:
            combined = past.drop_duplicates(
                subset=["granularity", "timestamp_ist"], keep="first")
            combined = combined.sort_values("timestamp_ist").reset_index(drop=True)
            xlsx_path, ok = _write_excel(combined)
            return {"added_second": 0, "added_minute": 0, "added_hour": 0,
                    "total_second": 0,
                    "total_minute": int((combined["granularity"] == "minute").sum()),
                    "total_hour": int((combined["granularity"] == "hour").sum()),
                    "seed_hours": int((combined["granularity"] == "hour").sum()),
                    "migrated_csv": False, "xlsx_ok": ok,
                    "csv_path": CSV_PATH, "xlsx_path": xlsx_path}
        return {"added_second": 0, "added_minute": 0, "added_hour": 0,
                "total_second": 0, "total_minute": 0, "total_hour": 0,
                "seed_hours": 0, "migrated_csv": False, "xlsx_ok": False,
                "csv_path": CSV_PATH, "xlsx_path": XLSX_PATH}

    existing = _load_existing()
    if not existing.empty:
        ts = pd.to_datetime(existing["timestamp_ist"], format="ISO8601", utc=True)
        now_utc = pd.Timestamp(datetime.now(IST)).tz_convert("UTC")
        existing = existing[ts <= now_utc].reset_index(drop=True)
    past = _build_past_hour_rows()
    combined = pd.concat([existing, past, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["granularity", "timestamp_ist"],
                                        keep="first")
    combined = combined.sort_values("timestamp_ist").reset_index(drop=True)
    xlsx_path, ok = _write_excel(combined)

    migrated_csv = False
    if ok and os.path.exists(CSV_PATH):
        try:
            os.remove(CSV_PATH)
            migrated_csv = True
        except Exception:
            pass

    def total(g):
        return int((combined["granularity"] == g).sum())

    return {
        "added_second": counts["second"], "added_minute": counts["minute"],
        "added_hour": counts["hour"],
        "total_second": total("second"), "total_minute": total("minute"),
        "total_hour": total("hour"),
        "seed_hours": int((past["granularity"] == "hour").sum()) if len(past) else 0,
        "migrated_csv": migrated_csv, "xlsx_ok": ok,
        "csv_path": CSV_PATH, "xlsx_path": xlsx_path,
    }


if __name__ == "__main__":
    from rt_stream import build_telemetry
    sec = build_telemetry([])
    s = append_history(sec)
    for k, v in s.items():
        print(f"{k}: {v}")