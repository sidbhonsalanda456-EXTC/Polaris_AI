"""Live telemetry recorder.

Streams a new AI telemetry reading EVERY PASSING SECOND into the growing
history files (data/telemetry_history.csv + data/ai_telemetry_history.xlsx)
without needing to press 'Run' again. Minutes and hours are stored as the
average of their seconds. Run standalone (python live_recorder.py) or start
it automatically with the web dashboard (app.py does this already).
"""
import csv
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import rt_stream
import solar_utils
from telemetry_history import (CSV_PATH, XLSX_PATH, COLUMNS, WEATHER_COLS,
                               NUMERIC_COLS, _write_excel)

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARKER_PATH = os.path.join(BASE_DIR, "data", ".live_recorder_active")

_WEATHER_KEYS = ["temperature_c", "feels_like_c", "wind_speed_mps",
                 "wind_direction_deg", "cloud_cover_pct", "solar_irradiance_wm2",
                 "snowfall_mm", "precipitation_mm", "humidity_pct", "pressure_hpa"]


def _current_weather_baseline():
    try:
        from weather_service import load_weather_cache, generate_fallback_weather
        cache = load_weather_cache()
        if cache and cache.get("current"):
            return cache
        return generate_fallback_weather()
    except Exception:
        return {}


def _time_floor_for(ts, freq):
    base = ts.replace(second=0, microsecond=0)
    if freq == "minute":
        return base
    return base.replace(minute=0)


class LiveTelemetryRecorder:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._known = set()
        self._min_buf = []
        self._cur_minute = None
        self._hour_buf = []
        self._cur_hour = None
        self._basis_ts = None
        self._basis = None
        self._baseline = _current_weather_baseline()
        self.counts = {"second": 0, "minute": 0, "hour": 0}
        self.started_at_ist = None
        self._load_known()

    # ---------------------------------------------------------------- helpers
    def _load_known(self):
        if not os.path.exists(CSV_PATH):
            return
        try:
            for g in ("second", "minute", "hour"):
                df = pd.read_csv(CSV_PATH)
                if "granularity" not in df.columns or "timestamp_ist" not in df.columns:
                    break
                self._known.update(
                    (g, str(ts)) for _, ts in df.loc[df["granularity"] == g, "timestamp_ist"].items())
                self.counts[g] = int((df["granularity"] == g).sum())
        except Exception:
            pass

    def _basis_for(self, ts):
        if (self._basis_ts is None or ts - self._basis_ts > timedelta(minutes=5)):
            try:
                self._basis = rt_stream._past_hour_basis(days=1)
            except Exception:
                self._basis = ({}, {})
            self._basis_ts = ts
        return self._basis

    def _entry(self, ts):
        past_w, past_r = self._basis_for(ts)
        k = ts.strftime("%Y-%m-%dT%H")
        rf = past_r.get(k)
        if rf is None:
            return None
        wf = past_w.get(k, {})
        current = self._baseline.get("current", {})
        return {
            "predicted_generation_kw": {src: rf.get(out, 0)
                                        for src, out in rt_stream.RES_KEY_MAP.items()},
            "predicted_demand_kw": rf.get("demand_kw", 0),
            "weather": {
                "temperature_c": wf.get("temperature_c", current.get("temperature_c")),
                "wind_speed_mps": wf.get("wind_speed_mps", current.get("wind_speed_mps")),
                "cloud_cover_pct": wf.get("cloud_cover_pct", current.get("cloud_cover_pct")),
                "solar_irradiance_wm2": wf.get("solar_irradiance_wm2", current.get("solar_irradiance_wm2")),
                "snowfall_mm": wf.get("snowfall_mm", current.get("snowfall_mm")),
            },
        }

    def _reading(self, ts):
        """One full merged row (weather + resources + demand) for this second."""
        f = self._entry(ts)
        current = self._baseline.get("current", {})
        w = rt_stream._weather_row(ts, f, current, seconds=True)
        r = rt_stream._resource_row(ts, f, seconds=True)
        return {**w, **{c: r[c] for c in r if c not in w}}

    def _append_rows(self, rows):
        """Append rows to CSV (thread-safe). Returns rows actually written."""
        written = []
        if not rows:
            return written
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        with self._lock:
            new_file = not os.path.exists(CSV_PATH)
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
                if new_file:
                    writer.writeheader()
                for row in rows:
                    key = (row.get("granularity"), str(row.get("timestamp_ist")))
                    if key in self._known:
                        continue
                    self._known.add(key)
                    self.counts[row.get("granularity")] = self.counts.get(row.get("granularity"), 0) + 1
                    writer.writerow({c: row.get(c, "") for c in COLUMNS})
                    written.append(row)
        return written

    def _rebuild_xlsx(self):
        try:
            if os.path.exists(CSV_PATH):
                df = pd.read_csv(CSV_PATH).reindex(columns=COLUMNS)
                _write_excel(df)
        except Exception:
            pass

    # ------------------------------------------------------------------ flow
    def _tick(self):
        now = datetime.now(IST)
        ts_key_second = now.isoformat()

        # --- second reading
        row = self._reading(now)
        row["granularity"] = "second"
        row["timestamp_ist"] = ts_key_second
        self._append_rows([row])

        # --- minute / hour rolling averages
        minute = _time_floor_for(now, "minute")
        hour = _time_floor_for(now, "hour")
        self._min_buf.append(row)
        self._hour_buf.append(row)

        crossed_minute = self._cur_minute is not None and minute != self._cur_minute
        crossed_hour = self._cur_hour is not None and hour != self._cur_hour
        if crossed_hour:
            self._flush_bucket(self._hour_buf, "hour", self._cur_hour)
            self._hour_buf = []
        if crossed_minute:
            self._flush_bucket(self._min_buf, "minute", self._cur_minute)
            self._min_buf = []
        self._cur_minute = minute
        self._cur_hour = hour

        if crossed_hour or crossed_minute:
            self._rebuild_xlsx()

    def _flush_bucket(self, buf, granularity, bucket_ts):
        if not buf:
            return
        avg = {c: round(float(pd.Series([r.get(c) or 0 for r in buf]).mean()), 2)
               for c in NUMERIC_COLS}
        row = {"granularity": granularity,
               "timestamp_ist": bucket_ts.strftime("%Y-%m-%dT%H:%M:%S+05:30")
               if granularity == "minute"
               else bucket_ts.strftime("%Y-%m-%dT%H:00:00+05:30"),
               **avg}
        self._append_rows([row])

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(1.0)

    # ----------------------------------------------------------------- public
    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return self
        self.started_at_ist = datetime.now(IST)
        os.makedirs(os.path.dirname(MARKER_PATH), exist_ok=True)
        with open(MARKER_PATH, "w") as fh:
            fh.write(str(os.getpid()))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        try:
            if os.path.exists(MARKER_PATH):
                os.remove(MARKER_PATH)
        except Exception:
            pass

    def status(self):
        return {
            "recording": self._thread is not None and self._thread.is_alive(),
            "started_at_ist": self.started_at_ist.isoformat() if self.started_at_ist else None,
            "counts": dict(self.counts),
            "csv_path": CSV_PATH,
            "xlsx_path": XLSX_PATH,
        }


_RECORDER = None


def get_recorder():
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = LiveTelemetryRecorder()
    return _RECORDER


def recorder_active():
    return os.path.exists(MARKER_PATH)


if __name__ == "__main__":
    rec = get_recorder()
    rec.start()
    print("=" * 60)
    print("  LIVE TELEMETRY RECORDER - started")
    print(f"  Recording every passing second to data/telemetry_history.csv")
    print(f"  Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        last = None
        while True:
            time.sleep(1)
            st = rec.status()
            if st["counts"] != last:
                last = dict(st["counts"])
                print(f"  [{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}] "
                      f"totals: {st['counts']['second']} seconds | "
                      f"{st['counts']['minute']} minutes (avg) | "
                      f"{st['counts']['hour']} hours (avg)")
    except KeyboardInterrupt:
        rec.stop()
        print("  Recorder stopped. History saved.")