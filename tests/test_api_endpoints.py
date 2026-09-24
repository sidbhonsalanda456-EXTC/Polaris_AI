import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app, PROJECT_ROOT
from database.database import StationDatabase

client = TestClient(app)

def test_api_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data
    assert "total_generation_kw" in data["data"]
    assert "battery_soc_pct" in data["data"]

def test_api_digital_twin_endpoint():
    response = client.get("/api/twin")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "thingId" in data["data"]
    assert "features" in data["data"]
    assert "solar_system" in data["data"]["features"]
    assert "battery" in data["data"]["features"]

def test_api_ai_status_endpoint():
    response = client.get("/api/ai")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "current_action" in data["data"]
    assert "current_reason" in data["data"]

def test_api_alerts_endpoint():
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "active_alerts" in data

def test_api_summary_endpoint():
    response = client.get("/api/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "summary" in data

def test_api_two_part_energy_endpoint():
    response = client.get("/api/energy/two-part")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "part_1_renewable" in data
    assert "part_2_non_renewable" in data
    assert "dynamic_input_stream" in data
    assert "solar_power_kw" in data["part_1_renewable"]
    assert "primary_diesel_kw" in data["part_2_non_renewable"]

def test_api_stream_mode_and_input():
    # Test setting stream mode to DYNAMIC_SYNTHETIC
    res_mode = client.post("/api/stream/mode", json={"mode": "DYNAMIC_SYNTHETIC"})
    assert res_mode.status_code == 200
    assert res_mode.json()["mode"] == "DYNAMIC_SYNTHETIC"

    # Test injecting manual input
    res_input = client.post("/api/stream/input", json={"temperature": -30.0, "wind": 15.0, "solar": 500.0})
    assert res_input.status_code == 200

def test_api_controls():
    # Stop simulation
    res_stop = client.post("/api/simulation/stop")
    assert res_stop.status_code == 200
    assert res_stop.json()["is_running"] is False

    # Start simulation
    res_start = client.post("/api/simulation/start")
    assert res_start.status_code == 200
    assert res_start.json()["is_running"] is True

    # Set speed
    res_speed = client.post("/api/simulation/speed", json={"speed": 2.0})
    assert res_speed.status_code == 200
    assert res_speed.json()["speed"] == 2.0

    # Set mode
    res_mode = client.post("/api/simulation/mode", json={"mode": "BASELINE"})
    assert res_mode.status_code == 200
    assert res_mode.json()["mode"] == "BASELINE"

    # Reset
    res_reset = client.post("/api/simulation/reset")
    assert res_reset.status_code == 200

def test_database_persistence(tmp_path):
    test_db = StationDatabase(db_path=str(tmp_path / "test.db"))
    test_telemetry = {
        "step": 1,
        "timestamp": "2026-07-15T12:00:00",
        "solar_power_kw": 25.0,
        "wind_power_kw": 30.0,
        "total_generation_kw": 55.0,
        "total_station_load_kw": 50.0,
        "critical_load_kw": 35.0,
        "flexible_load_kw": 15.0,
        "battery_soc_pct": 72.0,
        "battery_power_kw": 5.0,
        "battery_temperature_c": 11.5,
        "generator_power_kw": 0.0,
        "power_balance_kw": 5.0,
        "renewable_percentage": 100.0,
        "temperature_c": -20.0,
        "wind_speed_m_s": 8.0,
        "cloud_cover": 0.2,
        "weather_condition": "Clear",
        "ai_action": 1,
        "ai_action_name": "CHARGE BATTERY",
        "ai_action_reason": "Surplus renewable generation available.",
        "ai_reward": 8.5,
        "alerts": []
    }
    test_db.record_telemetry(test_telemetry)
    recent = test_db.get_recent_telemetry(limit=10)
    assert len(recent) == 1
    assert recent[0]["solar_power_kw"] == 25.0
    assert recent[0]["ai_action_name"] == "CHARGE BATTERY"

def test_api_integration_endpoint():
    response = client.get("/api/integration")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data
    manifest = data["data"]
    assert "modules" in manifest
    assert "ai_agent" in manifest["modules"]
    assert "data_pipeline" in manifest["modules"]
    assert "energy_optimizer" in manifest["modules"]
    assert "digital_twin_ui" in manifest["modules"]
    assert manifest["modules"]["ai_agent"]["status"] == "OPERATIONAL"
    assert manifest["modules"]["digital_twin_ui"]["status"] == "OPERATIONAL"
    assert "team_roster" in manifest
    assert "prachi" in manifest["team_roster"]
    assert "aashika" in manifest["team_roster"]
    assert "bhoomika" in manifest["team_roster"]
    assert "diya" in manifest["team_roster"]
    assert "hitesh" in manifest["team_roster"]

def test_api_admin_resource_and_config():
    # Test getting admin resources
    res = client.get("/admin/resources")
    assert res.status_code == 200
    catalog = res.json()
    assert "renewable_generation" in catalog
    assert "storage" in catalog

    # Test updating a resource using frontend aliases and expanded fields
    put_res = client.put("/admin/resources/solar", json={"online": True, "output_kw": 180, "condition": "GOOD"})
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["resource"]["id"] == "solar_pv"
    assert data["resource"]["enabled"] is True

    # Test updating battery via station config
    cfg_res = client.put("/admin/config", json={"battery_soc": 78, "battery_enabled": True, "battery_state": "CHARGING"})
    assert cfg_res.status_code == 200

def test_polaris_pages_live_integration():
    # Verify that polaris resource pages contain live fetch hooks instead of pure Math.random
    pages = [
        "solar.html", "wind.html", "battery.html", "generator.html",
        "hydro.html", "hydrogen.html", "marine.html", "biomass.html",
        "solarthermal.html", "chp.html", "passive-solar.html", "geothermal.html",
        "disaster.html", "backup-intelligence.html", "admin.html"
    ]
    polaris_dir = os.path.join(PROJECT_ROOT, "dashboard", "polaris")
    for p in pages:
        file_path = os.path.join(polaris_dir, p)
        assert os.path.exists(file_path), f"Missing page: {p}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "fetch(" in content or "apiGet(" in content, f"{p} missing live api fetch hook"

def test_api_ncpor_stations():
    # Test station catalog retrieval
    res = client.get("/api/stations")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "stations" in data
    assert len(data["stations"]) >= 3
    station_ids = [s["id"] for s in data["stations"]]
    assert "bharati" in station_ids
    assert "maitri" in station_ids
    assert "himadri" in station_ids

    # Test selecting Maitri station
    sel_res = client.post("/api/stations/select", json={"station": "maitri"})
    assert sel_res.status_code == 200
    station_meta = sel_res.json()["station"]
    assert station_meta["id"] == "maitri"
    assert "Maitri" in station_meta["name"]
    assert "NCPOR" in station_meta["agency"]

    # Re-select Bharati station
    sel_res2 = client.post("/api/stations/select", json={"station": "bharati"})
    assert sel_res2.status_code == 200
    assert sel_res2.json()["station"]["id"] == "bharati"

def test_api_showcase_scenario():
    # Test triggering showcase scenario
    res = client.post("/api/showcase/scenario", json={"scenario": "solar_peak"})
    assert res.status_code == 200
    assert res.json()["data"]["scenario"] == "solar_peak"

    # Reset baseline
    res_reset = client.post("/api/showcase/scenario", json={"scenario": "normal"})
    assert res_reset.status_code == 200




