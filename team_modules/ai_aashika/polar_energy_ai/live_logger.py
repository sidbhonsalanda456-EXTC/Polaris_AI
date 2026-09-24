import csv
import os
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from safe_write import write_csv
from telemetry_history import COLUMNS, WEATHER_COLS, RESOURCE_COLS
from rt_stream import (_weather_row, _resource_row, _forecast_by_hour,
                       _past_hour_basis, RES_KEY_MAP, _inject_live_seconds)

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_PATH = os.path.join(BASE_DIR, "data", "live_telemetry.csv")
RUNS_DIR = os.path.join(BASE_DIR, "data", "runs_history")
RUNS_SUMMARY = os.path.join(RUNS_DIR, "runs_summary.csv")


class LiveTelemetry:
    """REAL-time per-second telemetry collector.

    The instant a run starts, one reading per passing second is stamped with
    the ACTUAL collection time (IST). No future timestamps are ever created.
    Collected seconds live in self.seconds (authoritative) - no temporary file
    is written anymore; everything goes into the single history workbook
    (data/ai_telemetry_history.xlsx) once the run's analysis completes.

    When a run finishes, its whole session (live seconds + minutes + hours) is
    archived into data/runs_history/run_<start>.csv, and a row is appended to
    runs_summary.csv. Whenever the app/workbook is opened again (a new run
    starts), any leftover previous-session file that was never archived is
    automatically moved into the history section first, so nothing is lost."""

    def __init__(self, start_time=None):
        self.t0 = start_time or datetime.now(IST)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_written = -1
        self._thread = None
        self._captured = False
        self.seconds = []
        self.forecast = []
        self.current = {}
        self._keyed = {}
        self._keys = []
        self._past_w = {}
        self._past_r = {}

    # ---- live context ----
    def set_context(self, forecast, current=None):
        self.forecast = forecast or []
        self.current = current or {}
        try:
            self._keyed, self._keys = _forecast_by_hour(self.forecast)
        except Exception:
            self._keyed, self._keys = {}, []
        try:
            self._past_w, self._past_r = _past_hour_basis()
        except Exception:
            pass

    def _f(self, ts):
        k = ts.strftime("%Y-%m-%dT%H")
        f = self._keyed.get(k)
        if f is None and self._past_r:
            rf = self._past_r.get(k)
            if rf is not None:
                wf = self._past_w.get(k, {})
                f = {
                    "predicted_generation_kw": {src: rf.get(out, 0)
                                                for src, out in RES_KEY_MAP.items()},
                    "predicted_demand_kw": rf.get("demand_kw", 0),
                    "weather": {key: wf.get(key) for key in (
                        "temperature_c", "wind_speed_mps", "cloud_cover_pct",
                        "solar_irradiance_wm2", "snowfall_mm")},
                }
        if f is None and self._keys:
            f = self._keyed[self._keys[0]]
        return f

    def _row(self, ts):
        f = self._f(ts)
        w = _weather_row(ts, f, self.current, seconds=True)
        r = _resource_row(ts, f, seconds=True)
        row = {"granularity": "second", "timestamp_ist": ts.isoformat()}
        for c in WEATHER_COLS:
            row[c] = w.get(c)
        for c in RESOURCE_COLS:
            row[c] = r.get(c)
        return row

    # ---- storage ----
    def _append(self, row):
        with self._lock:
            self.seconds.append(row)

    # ---- start / rollover previous session ----
    def start(self):
        """Start capturing from THIS run's start moment. Any previous session's
        unarchived legacy live file is first saved into the history section."""
        self._rollover_previous_session()
        self._append(self._row(self.t0))
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()
        return self

    def _rollover_previous_session(self):
        """If a legacy live file from a previous session was never archived
        (e.g. the app was closed mid-run), save it into the history section
        before it is deleted - nothing is left behind, no new file is created."""
        if not os.path.exists(LIVE_PATH):
            return
        try:
            prev = pd.read_csv(LIVE_PATH)
        except Exception:
            return
        prev = prev[prev["granularity"] == "second"] if not prev.empty else prev
        if prev.empty:
            return
        try:
            ts0 = pd.to_datetime(prev["timestamp_ist"].iloc[0],
                                 format="ISO8601", utc=True)
            ts1 = pd.to_datetime(prev["timestamp_ist"].iloc[-1],
                                 format="ISO8601", utc=True)
        except Exception:
            return
        stamp = ts0.astimezone(IST).strftime("%Y%m%d_%H%M%S")
        run_path = os.path.join(RUNS_DIR, f"run_{stamp}.csv")
        if os.path.exists(run_path):
            pass
        else:
            os.makedirs(RUNS_DIR, exist_ok=True)
            write_csv(prev, run_path)
            self._append_summary([{
                "run_start_ist": ts0.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "run_end_ist": ts1.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "seconds": len(prev), "minutes": 0, "hours": 0,
                "file": f"runs_history/run_{stamp}.csv",
            }])
        try:
            os.remove(LIVE_PATH)
        except Exception:
            pass

    def _tick(self):
        i = 1
        while not self._stop.wait(1.0):
            try:
                ts = self.t0 + timedelta(seconds=i)
                if ts <= datetime.now(IST):
                    self._append(self._row(ts))
                    self._last_written = i
            except Exception:
                pass
            i += 1

    # ---- read / inject ----
    def snapshot_seconds(self):
        with self._lock:
            return list(self.seconds)

    def inject_seconds(self, sections):
        return _inject_live_seconds(sections, self.snapshot_seconds())

    def split_seconds(self):
        w, r = [], []
        for row in self.seconds:
            wrow = {"granularity": "second", "timestamp_ist": row["timestamp_ist"]}
            rrow = {"granularity": "second", "timestamp_ist": row["timestamp_ist"]}
            for c in WEATHER_COLS:
                wrow[c] = row.get(c)
            for c in RESOURCE_COLS:
                rrow[c] = row.get(c)
            w.append(wrow)
            r.append(rrow)
        return w, r

    def snapshot_sections(self, sections):
        d = {"weather": list(sections.get("weather", [])),
             "resources": list(sections.get("resources", [])),
             "failover": sections.get("failover", {"failures": [], "rows": []})}
        return _inject_live_seconds(d, self.snapshot_seconds())

    # ---- finalize ----
    def capture(self):
        """Stop collecting and close any gap. Collects the REAL seconds that
        passed between Run-start and now (in-memory list). Idempotent."""
        if self._captured:
            return self.seconds
        self._captured = True
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        end_i = int((datetime.now(IST) - self.t0).total_seconds())
        for i in range(len(self.seconds), end_i + 1):
            try:
                ts = self.t0 + timedelta(seconds=i)
                if ts <= datetime.now(IST):
                    self._append(self._row(ts))
                    self._last_written = i
            except Exception:
                pass
        return self.seconds

    def count(self):
        return len(self.seconds)

    def _append_summary(self, rows):
        header = ["run_start_ist", "run_end_ist", "seconds", "minutes",
                  "hours", "file"]
        os.makedirs(os.path.dirname(RUNS_SUMMARY), exist_ok=True)
        write_header = not os.path.exists(RUNS_SUMMARY)
        try:
            with open(RUNS_SUMMARY, "a", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=header)
                if write_header:
                    w.writeheader()
                w.writerows(rows)
        except PermissionError:
            print(f"  [!] data/runs_history/runs_summary.csv is locked "
                  f"(open in Excel?) - summary row skipped.")

    def archive(self, sections=None):
        """Save THIS session (live seconds collected + minutes + hours from the
        sections) into data/runs_history/run_<start>.csv and append a row to
        runs_summary.csv. Returns a summary dict."""
        sec_df = (pd.DataFrame(list(self.snapshot_seconds()))
                  if self.seconds else pd.DataFrame(columns=COLUMNS))
        sec_df = sec_df.drop_duplicates(subset="timestamp_ist") \
            if not sec_df.empty else sec_df

        extra = pd.DataFrame()
        if sections:
            from telemetry_history import _merge_sections
            merged = _merge_sections(sections)
            extra = merged[merged["granularity"].isin(["minute", "hour"])]
            extra = extra.drop_duplicates(subset=["granularity", "timestamp_ist"]) \
                if not extra.empty else extra

        run_df = pd.concat([sec_df, extra], ignore_index=True)
        if not run_df.empty:
            run_df = run_df.drop_duplicates(
                subset=["granularity", "timestamp_ist"], keep="first")
            run_df = run_df.sort_values("timestamp_ist").reset_index(drop=True)

        stamp = self.t0.strftime("%Y%m%d_%H%M%S")
        os.makedirs(RUNS_DIR, exist_ok=True)
        run_path = os.path.join(RUNS_DIR, f"run_{stamp}.csv")
        write_csv(run_df, run_path)

        end = datetime.now(IST)
        counts = {
            "seconds": int((run_df["granularity"] == "second").sum()) if len(run_df) else 0,
            "minutes": int((run_df["granularity"] == "minute").sum()) if len(run_df) else 0,
            "hours": int((run_df["granularity"] == "hour").sum()) if len(run_df) else 0,
        }
        summary_rows = [{
            "run_start_ist": self.t0.strftime("%Y-%m-%d %H:%M:%S"),
            "run_end_ist": end.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": counts["seconds"], "minutes": counts["minutes"],
            "hours": counts["hours"], "file": f"runs_history/run_{stamp}.csv",
        }]
        self._append_summary(summary_rows)

        run_count = 0
        if os.path.exists(RUNS_SUMMARY):
            try:
                with open(RUNS_SUMMARY, "r", encoding="utf-8") as fh:
                    run_count = max(0, sum(1 for _ in fh) - 1)
            except Exception:
                run_count = 0

        return {
            "run_file": run_path,
            "run_start_ist": summary_rows[0]["run_start_ist"],
            "run_end_ist": summary_rows[0]["run_end_ist"],
            "seconds": counts["seconds"], "minutes": counts["minutes"],
            "hours": counts["hours"], "run_count": run_count,
            "live_path": None,
        }

    def finish(self, sections=None):
        """Convenience wrapper: capture real seconds, then archive the session."""
        self.capture()
        return self.archive(sections or {})