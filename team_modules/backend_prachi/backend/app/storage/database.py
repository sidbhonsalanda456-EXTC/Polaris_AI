"""SQLite storage: the single source of truth for the whole system.

Stores raw sensor readings, the latest AI/optimizer inputs and optimizer results
so both the AI module and the UI can read consistent current state.
"""
import sqlite3
import os
from typing import List, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BASE, "data")
DEFAULT_DB = os.path.join(DATA_DIR, "polar_station.db")


class Database:
    def __init__(self, db_path: str = DEFAULT_DB):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    timestamp TEXT PRIMARY KEY,
                    temperature_c REAL, humidity_pct REAL,
                    wind_speed_mps REAL, wind_direction_deg REAL,
                    solar_irradiance_wm2 REAL, solar_status TEXT, wind_status TEXT,
                    solar_generation_kw REAL, wind_generation_kw REAL,
                    energy_demand_kw REAL, battery_soc_pct REAL, generator_status TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS optimizer_inputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, horizon TEXT,
                    predicted_demand_kw REAL, predicted_solar_kw REAL,
                    predicted_wind_kw REAL, renewable_generation_kw REAL,
                    predicted_deficit_kw REAL, solar_status TEXT, wind_status TEXT,
                    available_resources TEXT, recommendation TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS optimizer_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, strategy TEXT, battery_charge_kw REAL,
                    battery_discharge_kw REAL, generator_kw REAL,
                    load_shed_kw REAL, notes TEXT
                )
            """)

    # ---- raw readings ----
    def insert_many(self, readings: List[dict]) -> int:
        cols = list(readings[0].keys())
        q = (f"INSERT OR IGNORE INTO sensor_readings ({','.join(cols)}) "
             f"VALUES ({','.join('?' for _ in cols)})")
        rows = [[r.get(c) for c in cols] for r in readings]
        with self.conn:
            self.conn.executemany(q, rows)
        return len(readings)

    def insert_one(self, reading: dict) -> bool:
        return self.insert_many([reading]) > 0

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM sensor_readings").fetchone()["c"]

    def latest(self, n: int = 1, table: str = "sensor_readings") -> List[dict]:
        rows = self.conn.execute(
            f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows][::-1]

    def fetch(self, limit: int = 100, offset: int = 0) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sensor_readings ORDER BY timestamp LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def fetch_aggregated(self, granularity: str, limit: int = 100,
                         offset: int = 0) -> List[dict]:
        """Aggregate raw seconds into 1min/1hour buckets directly in SQL."""
        fmt = "%Y-%m-%d %H:%M" if granularity == "1min" else "%Y-%m-%d %H:00"
        expr = f"strftime('{fmt}', timestamp)"
        q = f"""
            SELECT {expr} AS bucket,
                   ROUND(AVG(temperature_c),2)   AS temperature_c,
                   ROUND(AVG(humidity_pct),1)    AS humidity_pct,
                   ROUND(AVG(wind_speed_mps),2)  AS wind_speed_mps,
                   ROUND(AVG(wind_direction_deg),1) AS wind_direction_deg,
                   ROUND(AVG(solar_irradiance_wm2),1) AS solar_irradiance_wm2,
                   ROUND(AVG(solar_generation_kw),4)  AS solar_generation_kw,
                   ROUND(AVG(wind_generation_kw),4)   AS wind_generation_kw,
                   ROUND(AVG(energy_demand_kw),3)     AS energy_demand_kw,
                   ROUND(AVG(battery_soc_pct),1)      AS battery_soc_pct,
                   COUNT(*) AS n_seconds
            FROM sensor_readings
            GROUP BY bucket
            ORDER BY bucket LIMIT ? OFFSET ?
        """
        rows = self.conn.execute(q, (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    # ---- optimizer ----
    def insert_optimizer_input(self, data: dict):
        cols = ["timestamp", "horizon", "predicted_demand_kw", "predicted_solar_kw",
                "predicted_wind_kw", "renewable_generation_kw", "predicted_deficit_kw",
                "solar_status", "wind_status", "available_resources", "recommendation"]
        q = (f"INSERT INTO optimizer_inputs ({','.join(cols)}) "
             f"VALUES ({','.join('?' for _ in cols)})")
        with self.conn:
            self.conn.execute(q, [data.get(c) for c in cols])

    def insert_optimizer_result(self, data: dict):
        cols = ["timestamp", "strategy", "battery_charge_kw", "battery_discharge_kw",
                "generator_kw", "load_shed_kw", "notes"]
        q = (f"INSERT INTO optimizer_results ({','.join(cols)}) "
             f"VALUES ({','.join('?' for _ in cols)})")
        with self.conn:
            self.conn.execute(q, [data.get(c) for c in cols])

    def last_optimizer_result(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM optimizer_results ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def close(self):
        self.conn.close()
