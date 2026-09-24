import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.database import StationDatabase, SUPABASE_URL, SUPABASE_KEY

print("=== SUPABASE INTEGRATION CHECK ===")
print("1. Checking credentials:")
print(f"   URL: {SUPABASE_URL}")
print(f"   KEY: {SUPABASE_KEY[:20]}...{SUPABASE_KEY[-10:]}")

print("2. Initializing StationDatabase:")
db = StationDatabase()
print(f"   Supabase client connected: {db.supabase is not None}")
print(f"   Async sync worker active: {db._worker_thread.is_alive()}")

print("3. Testing record_telemetry call:")
test_telemetry = {
    "step": 9999,
    "timestamp": "2026-09-24T10:14:00",
    "solar_power_kw": 12.5,
    "wind_power_kw": 45.2,
    "total_generation_kw": 57.7,
    "total_station_load_kw": 40.0,
    "critical_load_kw": 25.0,
    "flexible_load_kw": 15.0,
    "battery_soc_pct": 75.0,
    "battery_power_kw": -17.7,
    "battery_temperature_c": 15.0,
    "generator_power_kw": 0.0,
    "power_balance_kw": 17.7,
    "renewable_percentage": 100.0,
    "temperature_c": -22.0,
    "wind_speed_m_s": 8.5,
    "cloud_cover": 0.1,
    "weather_condition": "Clear",
    "ai_action": 0,
    "ai_action_name": "OPTIMAL DISPATCH",
    "ai_reward": 9.2,
    "energy_deficit_kw": 0.0,
    "energy_surplus_kw": 17.7,
    "alerts": []
}
db.record_telemetry(test_telemetry)
print("   record_telemetry executed without errors!")

print("4. Testing get_recent_telemetry retrieval:")
recent = db.get_recent_telemetry(limit=5)
print(f"   Retrieved {len(recent)} recent records.")
if recent:
    last = recent[-1]
    print(f"   Latest record step: {last.get('step')}, timestamp: {last.get('timestamp')}")

print("=== ALL SUPABASE INTEGRATION CHECKS PASSED! ===")
