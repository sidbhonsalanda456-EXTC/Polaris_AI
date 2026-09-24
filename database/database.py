import os
import sqlite3
import threading
import queue
import time
import datetime
from typing import Dict, Any, List, Optional

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = Any

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "station_telemetry.db"
)

# Supabase cloud credentials
DEFAULT_SUPABASE_URL = "https://eudzbkzpmvpatfbxnuda.supabase.co"
DEFAULT_SUPABASE_KEY = "sb_publishable_Y55I_IrL0f3j8YjSpZurQA_UKg8RHMC"

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or DEFAULT_SUPABASE_URL
SUPABASE_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or os.environ.get("SUPABASE_KEY") or DEFAULT_SUPABASE_KEY


class StationDatabase:
    """
    Hybrid Cloud + Edge Database for Polar Station Telemetry:
    1. Primary cloud database: Supabase PostgreSQL (PostgREST API).
    2. Zero-latency local SQLite fallback for resilient polar operations & offline evaluation.
    3. Asynchronous non-blocking background synchronization worker so simulation
       time-series clock ticks are NEVER delayed or jittered by network I/O.
    """
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

        # Supabase Cloud Client
        self.supabase_url = SUPABASE_URL
        self.supabase_key = SUPABASE_KEY
        self.supabase: Optional[Client] = None
        self._supabase_enabled = HAS_SUPABASE and bool(self.supabase_url and self.supabase_key)
        
        # Don't sync to cloud if running an isolated unit test with temporary DB
        self._is_test_instance = (db_path != DEFAULT_DB_PATH)

        if self._supabase_enabled and not self._is_test_instance:
            try:
                self.supabase = create_client(self.supabase_url, self.supabase_key)
                print(f"[Supabase] Connected to project: {self.supabase_url}")
            except Exception as e:
                print(f"[Supabase] Notice: Client init deferred ({e})")
                self.supabase = None

        # Asynchronous non-blocking cloud sync queue
        self._sync_queue: queue.Queue = queue.Queue(maxsize=2000)
        self._stop_worker = threading.Event()
        self._worker_thread = threading.Thread(target=self._supabase_worker, daemon=True, name="SupabaseSyncWorker")
        self._worker_thread.start()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Telemetry time-series table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step INTEGER,
                timestamp TEXT,
                solar_power_kw REAL,
                wind_power_kw REAL,
                total_generation_kw REAL,
                total_station_load_kw REAL,
                critical_load_kw REAL,
                flexible_load_kw REAL,
                battery_soc_pct REAL,
                battery_power_kw REAL,
                battery_temperature_c REAL,
                generator_power_kw REAL,
                power_balance_kw REAL,
                renewable_percentage REAL,
                temperature_c REAL,
                wind_speed_m_s REAL,
                cloud_cover REAL,
                weather_condition TEXT,
                ai_action INTEGER,
                ai_action_name TEXT,
                ai_reward REAL,
                energy_deficit_kw REAL,
                energy_surplus_kw REAL
            )
            """)

            # Alerts table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_code TEXT,
                severity TEXT,
                title TEXT,
                message TEXT,
                timestamp TEXT
            )
            """)

            # AI decision log
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step INTEGER,
                timestamp TEXT,
                action INTEGER,
                action_name TEXT,
                reason TEXT,
                reward REAL
            )
            """)

            # Training history
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                episode INTEGER,
                current_reward REAL,
                average_reward REAL,
                best_reward REAL,
                progress_pct REAL,
                critical_availability_pct REAL,
                renewable_utilization_pct REAL
            )
            """)

            conn.commit()
            conn.close()

    def _supabase_worker(self):
        """
        Background worker that drains the sync queue and pushes records to Supabase.
        Ensures zero blocking on the main station simulation loop.
        """
        while not self._stop_worker.is_set():
            try:
                task = self._sync_queue.get(timeout=1.0)
                if not task:
                    continue
                
                table_name, payload = task
                if self.supabase:
                    try:
                        self.supabase.table(table_name).insert(payload).execute()
                    except Exception as e:
                        # If table not yet created in Supabase (PGRST205) or network blip, handle cleanly
                        pass
                self._sync_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def record_telemetry(self, telemetry: Dict[str, Any]):
        """
        Record instantaneous time-series telemetry.
        Persists immediately to local SQLite and queues async write to Supabase.
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO telemetry (
                step, timestamp, solar_power_kw, wind_power_kw, total_generation_kw,
                total_station_load_kw, critical_load_kw, flexible_load_kw,
                battery_soc_pct, battery_power_kw, battery_temperature_c,
                generator_power_kw, power_balance_kw, renewable_percentage,
                temperature_c, wind_speed_m_s, cloud_cover, weather_condition,
                ai_action, ai_action_name, ai_reward, energy_deficit_kw, energy_surplus_kw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                telemetry.get("step", 0),
                str(telemetry.get("timestamp", "")),
                float(telemetry.get("solar_power_kw", 0.0)),
                float(telemetry.get("wind_power_kw", 0.0)),
                float(telemetry.get("total_generation_kw", 0.0)),
                float(telemetry.get("total_station_load_kw", 0.0)),
                float(telemetry.get("critical_load_kw", 0.0)),
                float(telemetry.get("flexible_load_kw", 0.0)),
                float(telemetry.get("battery_soc_pct", 0.0)),
                float(telemetry.get("battery_power_kw", 0.0)),
                float(telemetry.get("battery_temperature_c", 0.0)),
                float(telemetry.get("generator_power_kw", 0.0)),
                float(telemetry.get("power_balance_kw", 0.0)),
                float(telemetry.get("renewable_percentage", 0.0)),
                float(telemetry.get("temperature_c", 0.0)),
                float(telemetry.get("wind_speed_m_s", 0.0)),
                float(telemetry.get("cloud_cover", 0.0)),
                str(telemetry.get("weather_condition", "")),
                int(telemetry.get("ai_action", 0)),
                str(telemetry.get("ai_action_name", "")),
                float(telemetry.get("ai_reward", 0.0)),
                float(telemetry.get("energy_deficit_kw", 0.0)),
                float(telemetry.get("energy_surplus_kw", 0.0))
            ))

            # Record any new alerts
            for alert in telemetry.get("alerts", []):
                cursor.execute("""
                INSERT INTO alerts (alert_code, severity, title, message, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    str(alert.get("id", "")),
                    str(alert.get("severity", "info")),
                    str(alert.get("title", "")),
                    str(alert.get("message", "")),
                    str(alert.get("timestamp", ""))
                ))

            # Record AI decision
            if "ai_action" in telemetry:
                cursor.execute("""
                INSERT INTO ai_decisions (step, timestamp, action, action_name, reason, reward)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    telemetry.get("step", 0),
                    str(telemetry.get("timestamp", "")),
                    int(telemetry.get("ai_action", 0)),
                    str(telemetry.get("ai_action_name", "")),
                    str(telemetry.get("ai_action_reason", "")),
                    float(telemetry.get("ai_reward", 0.0))
                ))

            conn.commit()
            conn.close()

        # Queue async push to Supabase cloud
        if self._supabase_enabled and self.supabase and not self._is_test_instance:
            try:
                cloud_record = {
                    "step": telemetry.get("step", 0),
                    "timestamp": str(telemetry.get("timestamp", "")),
                    "solar_power_kw": float(telemetry.get("solar_power_kw", 0.0)),
                    "wind_power_kw": float(telemetry.get("wind_power_kw", 0.0)),
                    "total_generation_kw": float(telemetry.get("total_generation_kw", 0.0)),
                    "total_station_load_kw": float(telemetry.get("total_station_load_kw", 0.0)),
                    "critical_load_kw": float(telemetry.get("critical_load_kw", 0.0)),
                    "flexible_load_kw": float(telemetry.get("flexible_load_kw", 0.0)),
                    "battery_soc_pct": float(telemetry.get("battery_soc_pct", 0.0)),
                    "battery_power_kw": float(telemetry.get("battery_power_kw", 0.0)),
                    "battery_temperature_c": float(telemetry.get("battery_temperature_c", 0.0)),
                    "generator_power_kw": float(telemetry.get("generator_power_kw", 0.0)),
                    "power_balance_kw": float(telemetry.get("power_balance_kw", 0.0)),
                    "renewable_percentage": float(telemetry.get("renewable_percentage", 0.0)),
                    "temperature_c": float(telemetry.get("temperature_c", 0.0)),
                    "wind_speed_m_s": float(telemetry.get("wind_speed_m_s", 0.0)),
                    "cloud_cover": float(telemetry.get("cloud_cover", 0.0)),
                    "weather_condition": str(telemetry.get("weather_condition", "")),
                    "ai_action": int(telemetry.get("ai_action", 0)),
                    "ai_action_name": str(telemetry.get("ai_action_name", "")),
                    "ai_reward": float(telemetry.get("ai_reward", 0.0)),
                    "energy_deficit_kw": float(telemetry.get("energy_deficit_kw", 0.0)),
                    "energy_surplus_kw": float(telemetry.get("energy_surplus_kw", 0.0))
                }
                self._sync_queue.put_nowait(("telemetry", cloud_record))

                # Queue alerts
                for alert in telemetry.get("alerts", []):
                    self._sync_queue.put_nowait(("alerts", {
                        "alert_code": str(alert.get("id", "")),
                        "severity": str(alert.get("severity", "info")),
                        "title": str(alert.get("title", "")),
                        "message": str(alert.get("message", "")),
                        "timestamp": str(alert.get("timestamp", ""))
                    }))

                # Queue AI decision
                if "ai_action" in telemetry:
                    self._sync_queue.put_nowait(("ai_decisions", {
                        "step": telemetry.get("step", 0),
                        "timestamp": str(telemetry.get("timestamp", "")),
                        "action": int(telemetry.get("ai_action", 0)),
                        "action_name": str(telemetry.get("ai_action_name", "")),
                        "reason": str(telemetry.get("ai_action_reason", "")),
                        "reward": float(telemetry.get("ai_reward", 0.0))
                    }))
            except queue.Full:
                pass
            except Exception:
                pass

    def get_recent_telemetry(self, limit: int = 60) -> List[Dict[str, Any]]:
        """
        Retrieve recent time-series telemetry records in chronological order.
        Tries Supabase first; seamlessly falls back to local SQLite if cloud is unreachable.
        """
        if self._supabase_enabled and self.supabase and not self._is_test_instance:
            try:
                res = self.supabase.table("telemetry").select("*").order("id", desc=True).limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return list(reversed(res.data))
            except Exception:
                pass

        # Local SQLite fallback
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM telemetry ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in reversed(rows)]

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent station alerts from Supabase, with local SQLite fallback."""
        if self._supabase_enabled and self.supabase and not self._is_test_instance:
            try:
                res = self.supabase.table("alerts").select("*").order("id", desc=True).limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return res.data
            except Exception:
                pass

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM alerts ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def record_training_log(self, stats: Dict[str, Any]):
        """Record AI training step to local SQLite and Supabase."""
        ts = datetime.datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO training_history (
                timestamp, episode, current_reward, average_reward, best_reward,
                progress_pct, critical_availability_pct, renewable_utilization_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                stats.get("episode", 0),
                stats.get("current_reward", 0.0),
                stats.get("average_reward", 0.0),
                stats.get("best_reward", 0.0),
                stats.get("progress_pct", 0.0),
                stats.get("critical_availability_pct", 100.0),
                stats.get("renewable_utilization_pct", 0.0)
            ))
            conn.commit()
            conn.close()

        if self._supabase_enabled and self.supabase and not self._is_test_instance:
            try:
                self._sync_queue.put_nowait(("training_history", {
                    "timestamp": ts,
                    "episode": stats.get("episode", 0),
                    "current_reward": stats.get("current_reward", 0.0),
                    "average_reward": stats.get("average_reward", 0.0),
                    "best_reward": stats.get("best_reward", 0.0),
                    "progress_pct": stats.get("progress_pct", 0.0),
                    "critical_availability_pct": stats.get("critical_availability_pct", 100.0),
                    "renewable_utilization_pct": stats.get("renewable_utilization_pct", 0.0)
                }))
            except Exception:
                pass

    def get_training_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve training history records."""
        if self._supabase_enabled and self.supabase and not self._is_test_instance:
            try:
                res = self.supabase.table("training_history").select("*").order("id", desc=True).limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return list(reversed(res.data))
            except Exception:
                pass

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM training_history ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in reversed(rows)]
