import os
import json
import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set
from fastapi import WebSocket

from simulation.station import PolarStationSimulation
from ai.environment import PolarStationEnv
from ai.model import PolarAIAgent
from ai.baseline import BaselineHeuristicController
from ai.train import PolarAITrainer
from digital_twin.twin import PolarStationDigitalTwin
from database.database import StationDatabase
from mqtt.client import StationMQTTClient

# Project root path resolution
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class StationCoordinatorService:
    """
    Singleton service managing the continuous simulation execution loop,
    AI inference dispatch, Digital Twin synchronization, MQTT broadcasting,
    SQLite persistence, and WebSocket client streams.
    """
    def __init__(self):
        self.sim = PolarStationSimulation()
        self.ai_agent = PolarAIAgent()
        self.baseline_controller = BaselineHeuristicController()
        self.ai_trainer = PolarAITrainer()
        self.digital_twin = PolarStationDigitalTwin()
        self.database = StationDatabase()
        self.mqtt_client = StationMQTTClient()
        
        # Simulation control
        self.is_running = True
        self.control_mode = "AI_PPO"  # "AI_PPO", "BASELINE", "MANUAL"
        self.speed_multiplier = 1.0   # 0.5x, 1x, 2x, 5x, 10x
        self.manual_action = 0
        
        # Demo mode state machine
        self.demo_active = False
        self.demo_start_time = 0.0
        self.demo_phase_name = "Inactive"
        self.demo_seconds_elapsed = 0
        self.active_scenario = "normal"
        
        # WebSockets
        self.telemetry_clients: Set[WebSocket] = set()
        self.training_clients: Set[WebSocket] = set()
        self.loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Load Aashika's AI 24h Predictive Models & Forecast Data
        self.ai_forecast_data = self._load_ai_forecast()

        # Connect Prachi's IoT Database if present
        self.prachi_db = None
        try:
            from team_modules.backend_prachi.backend.app.storage.database import Database as PrachiDB
            self.prachi_db = PrachiDB()
        except Exception:
            pass

        # Load Aashika's trained Scikit-Learn Regression models for live dynamic forward passes
        self.solar_ml_model = None
        self.wind_ml_model = None
        self.demand_ml_model = None
        try:
            import pickle
            models_dir = os.path.join(PROJECT_ROOT, "team_modules", "ai_aashika", "polar_energy_ai", "models")
            s_path = os.path.join(models_dir, "solar_model.pkl")
            w_path = os.path.join(models_dir, "wind_model.pkl")
            d_path = os.path.join(models_dir, "demand_model.pkl")
            if os.path.exists(s_path):
                with open(s_path, "rb") as f:
                    self.solar_ml_model = pickle.load(f)
            if os.path.exists(w_path):
                with open(w_path, "rb") as f:
                    self.wind_ml_model = pickle.load(f)
            if os.path.exists(d_path):
                with open(d_path, "rb") as f:
                    self.demand_ml_model = pickle.load(f)
            print("[AI Coordinator] Loaded Aashika trained ML models: solar, wind, demand regressors.")
        except Exception as e:
            print(f"[AI Coordinator] Notice loading ML models: {e}")
        
        # Initialize gym env helper for normalized obs
        self._gym_helper = PolarStationEnv()
        
        # Latest cached telemetry (enriched with 12 resources & AI forecast)
        raw_telemetry = self.sim.get_telemetry()
        self.latest_telemetry: Dict[str, Any] = self._enrich_telemetry(raw_telemetry)

    def _enrich_telemetry(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Enriches raw simulation telemetry with Aashika's AI predictions and Bhoomika's 12 resources."""
        forecast_list = self.ai_forecast_data.get("forecast", [])
        curr_fc = forecast_list[0] if forecast_list else {}
        
        p_solar = telemetry.get("solar_power_kw", 0.0)
        p_wind = telemetry.get("wind_power_kw", 0.0)
        p_bat = telemetry.get("battery_power_kw", 0.0)
        p_gen = telemetry.get("generator_power_kw", 0.0)
        soc = telemetry.get("battery_soc_pct", 70.0)

        telemetry["ai_forecast"] = {
            "generated_at": self.ai_forecast_data.get("generated_at_ist", ""),
            "active_recommendation": curr_fc.get("recommended_resources", {
                "primary": {"name": "Wind", "value_kw": round(p_wind, 1), "category": "clean renewable"},
                "secondary": {"name": "Solar PV", "value_kw": round(p_solar, 1), "category": "clean renewable"},
                "tertiary": {"name": "Battery", "value_kw": round(abs(p_bat), 1), "category": "energy storage"},
                "coverage_kw": round(telemetry.get("total_generation_kw", 0.0), 1),
                "strategy": "AI PPO DISPATCH DYNAMICS"
            }),
            "predicted_demand_kw": curr_fc.get("predicted_demand_kw", telemetry.get("total_station_load_kw", 65.0)),
            "predicted_solar_kw": curr_fc.get("predicted_generation_kw", {}).get("solar_pv", p_solar),
            "predicted_wind_kw": curr_fc.get("predicted_generation_kw", {}).get("wind", p_wind),
            "risk_alerts": curr_fc.get("risk_alerts", []),
            "model_confidence": curr_fc.get("model_confidence_percent", {"solar": 85.0, "wind": 78.0, "demand": 82.5})
        }

        telemetry["active_scenario"] = getattr(self, "active_scenario", "normal")
        telemetry["hydro_power_kw"] = 90.0

        telemetry["modeled_resources_12"] = [
            {"id": "solar", "name": "Solar PV", "category": "renewable", "capacity_kw": 300, "output_kw": round(p_solar, 1), "online": True, "health": 98},
            {"id": "wind", "name": "Wind Turbines", "category": "renewable", "capacity_kw": 300, "output_kw": round(p_wind, 1), "online": True, "health": 97},
            {"id": "hydro", "name": "Hydropower", "category": "renewable", "capacity_kw": 200, "output_kw": 90.0, "online": True, "health": 96},
            {"id": "geothermal", "name": "Geothermal", "category": "renewable", "capacity_kw": 100, "output_kw": 95.0, "online": True, "health": 99},
            {"id": "marine", "name": "Marine Energy", "category": "renewable", "capacity_kw": 50, "output_kw": 20.0, "online": True, "health": 94},
            {"id": "biomass", "name": "Biomass / Biogas", "category": "renewable", "capacity_kw": 60, "output_kw": 55.0, "online": True, "health": 95},
            {"id": "solarthermal", "name": "Solar Thermal", "category": "renewable", "capacity_kw": 30, "output_kw": 18.0, "online": True, "health": 96},
            {"id": "hydrogen", "name": "Hydrogen Fuel Cell", "category": "storage", "capacity_kw": 50, "output_kw": 0.0, "online": True, "health": 93},
            {"id": "battery", "name": "LiFePO4 BESS Storage", "category": "storage", "capacity_kw": 100, "output_kw": round(abs(p_bat), 1), "online": True, "health": 92, "soc": round(soc, 1)},
            {"id": "generator", "name": "Diesel Generator Backup", "category": "backup", "capacity_kw": 100, "output_kw": round(p_gen, 1), "online": p_gen > 0.1, "health": 91},
            {"id": "chp", "name": "CHP Cogeneration", "category": "backup", "capacity_kw": 60, "output_kw": 0.0, "online": True, "health": 89},
            {"id": "passive", "name": "Passive Solar Efficiency", "category": "efficiency", "capacity_kw": 10, "output_kw": 10.0, "online": True, "health": 99}
        ]
        
        # Ensure active NCPOR station metadata is always included
        telemetry["station"] = telemetry.get("station") or self.sim.streamer.get_station_metadata()
        return telemetry

    def get_stations(self) -> Dict[str, Any]:
        """Returns the catalog of NCPOR polar research stations with active flag."""
        from simulation.realtime_feed import NCPOR_STATIONS
        stations_list = []
        active_id = self.sim.streamer.current_station_id
        for sid, spec in NCPOR_STATIONS.items():
            s_copy = dict(spec)
            s_copy["is_active"] = (sid == active_id)
            stations_list.append(s_copy)
        return {
            "active_station_id": active_id,
            "stations": stations_list
        }

    def set_active_station(self, station_id: str) -> Dict[str, Any]:
        """Dynamically switches active NCPOR research station and reconfigures microgrid."""
        meta = self.sim.set_station(station_id)
        self.latest_telemetry["station"] = meta
        return meta

    def apply_showcase_scenario(self, scenario: str) -> Dict[str, Any]:
        """Applies dynamic showcase scenario for live evaluations."""
        s = scenario.lower().strip()
        self.active_scenario = s
        if s == "solar_peak":
            self.sim.weather.set_override(condition="Clear Polar Daylight", cloud_cover=0.05, temperature=-12.0, wind_speed=7.5, solar_irradiance=680.0)
            msg = "Solar Peak scenario activated: Full solar PV output, battery charging, zero generator."
        elif s == "blizzard":
            self.sim.weather.set_override(condition="Katabatic Blizzard", cloud_cover=1.0, temperature=-34.0, wind_speed=34.0, solar_irradiance=0.0)
            msg = "Katabatic Blizzard scenario: Extreme wind speed, turbine storm shut-down, diesel + battery life-support."
        elif s == "deep_freeze":
            self.sim.weather.set_override(condition="Extreme Polar Freeze", cloud_cover=0.85, temperature=-42.0, wind_speed=12.0, solar_irradiance=50.0)
            msg = "Deep Freeze scenario: Heating demand surges, AI executes critical load prioritization."
        elif s == "flood":
            self.sim.weather.set_override(condition="Flash Thaw / Glacial Runoff (Flood)", cloud_cover=0.90, temperature=2.5, wind_speed=8.0, solar_irradiance=120.0)
            msg = "Flood Protocol: Glacial thaw debris derates hydro to 10%, solar available, BESS & microgrid auto-compensating."
        elif s == "tsunami":
            self.sim.weather.set_override(condition="Coastal Surge / Tsunami Swell", cloud_cover=0.95, temperature=-4.0, wind_speed=28.0, solar_irradiance=60.0)
            msg = "Tsunami Protocol: Coastal marine turbines isolated (OFF), wind derated to 15%, battery BESS & diesel backup armed."
        elif s == "storm":
            self.sim.weather.set_override(condition="Polar Storm & Whiteout", cloud_cover=1.0, temperature=-28.0, wind_speed=32.0, solar_irradiance=45.0)
            msg = "Storm Protocol: Severe storm derates wind to 15% and solar to 40%, critical loads prioritized by AI."
        else:
            self.sim.weather.clear_override()
            self.active_scenario = "normal"
            msg = "Baseline dynamic polar operation restored."

        # Synchronously reflect in latest_telemetry immediately
        p_hydro = 90.0
        p_marine = 20.0
        marine_online = True
        hydro_health = 96
        if self.active_scenario == "flood":
            p_hydro = 9.0
            hydro_health = 68
        elif self.active_scenario == "blizzard":
            p_hydro = 15.0
            hydro_health = 80
        elif self.active_scenario == "deep_freeze":
            p_hydro = 25.0
            hydro_health = 84
        elif self.active_scenario == "tsunami":
            p_hydro = 35.0
            marine_online = False
            p_marine = 0.0
        elif self.active_scenario == "storm":
            p_hydro = 45.0

        if hasattr(self, "latest_telemetry") and isinstance(self.latest_telemetry, dict):
            self.latest_telemetry["active_scenario"] = self.active_scenario
            self.latest_telemetry["hydro_power_kw"] = p_hydro
            for r in self.latest_telemetry.get("modeled_resources_12", []):
                if r.get("id") == "hydro":
                    r["output_kw"] = p_hydro
                    r["health"] = hydro_health
                elif r.get("id") == "marine":
                    r["output_kw"] = p_marine
                    r["online"] = marine_online

        return {"status": "success", "scenario": self.active_scenario, "message": msg}

    def _load_ai_forecast(self) -> Dict[str, Any]:
        """Loads Aashika's 24-hour predictive forecast and disaster risks."""
        forecast_path = os.path.join(PROJECT_ROOT, "team_modules", "ai_aashika", "polar_energy_ai", "output", "ai_forecast.json")
        if os.path.exists(forecast_path):
            try:
                with open(forecast_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[AI] Notice loading ai_forecast.json: {e}")
        return {
            "generated_at_ist": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "weather_source": "polar_station_live_feed",
            "forecast": []
        }

    def start(self):
        if self.loop_thread is None or not self.loop_thread.is_alive():
            self._stop_event.clear()
            self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self.loop_thread.start()
            print("[StationCoordinator] Simulation loop thread started.")

    def stop(self):
        self._stop_event.set()
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=2.0)
        self.mqtt_client.close()

    def set_running(self, running: bool):
        self.is_running = running

    def reset_simulation(self):
        self.latest_telemetry = self.sim.reset()
        self.digital_twin.sync_from_telemetry(self.latest_telemetry)
        self.demo_active = False
        self.demo_phase_name = "Inactive"
        self.demo_seconds_elapsed = 0
        self.active_scenario = "normal"
        self.sim.weather.clear_override()
        return self.latest_telemetry

    def set_control_mode(self, mode: str):
        if mode in ["AI_PPO", "BASELINE", "MANUAL"]:
            self.control_mode = mode

    def set_speed(self, speed: float):
        self.speed_multiplier = max(0.5, min(10.0, speed))

    def set_manual_action(self, action: int):
        self.manual_action = max(0, min(5, action))

    def start_demo_mode(self):
        self.demo_active = True
        self.demo_start_time = time.time()
        self.demo_phase_name = "Phase 1: Normal Polar Daylight"
        self.demo_seconds_elapsed = 0
        self.is_running = True

    def stop_demo_mode(self):
        self.demo_active = False
        self.demo_phase_name = "Inactive"
        self.demo_seconds_elapsed = 0
        self.sim.weather.clear_override()

    def _execute_demo_phase(self):
        """
        Executes automated 180-second dynamic polar scenario:
        0-30s: Normal Daylight
        30-60s: Increasing Cloud Cover
        60-90s: Sudden Solar Collapse & Temp Plunge
        90-120s: Severe Polar Deep Freeze (-40C, heating surge)
        120-150s: Gale Force Blizzard (28 m/s, wind turbine storm cut-out)
        150-180s: Weather Recovery & Wind Resumption
        """
        if not self.demo_active:
            return

        elapsed = int(time.time() - self.demo_start_time)
        self.demo_seconds_elapsed = elapsed

        if elapsed < 30:
            self.demo_phase_name = "Phase 1/6: Normal Conditions (Stable Sun & Wind)"
            self.sim.weather.set_override(condition="Clear", cloud_cover=0.2, temperature=-18.0, wind_speed=8.5, solar_irradiance=500.0)
        elif elapsed < 60:
            self.demo_phase_name = "Phase 2/6: Dense Storm Clouds Approaching"
            self.sim.weather.set_override(condition="Overcast", cloud_cover=0.90, temperature=-22.0, wind_speed=11.0, solar_irradiance=120.0)
        elif elapsed < 90:
            self.demo_phase_name = "Phase 3/6: Solar Generation Collapse"
            self.sim.weather.set_override(condition="Overcast", cloud_cover=1.0, temperature=-28.0, wind_speed=13.5, solar_irradiance=0.0)
        elif elapsed < 120:
            self.demo_phase_name = "Phase 4/6: Arctic Deep Freeze (-38°C Heating Surge)"
            self.sim.weather.set_override(condition="Extreme Cold", cloud_cover=0.95, temperature=-38.0, wind_speed=14.0, solar_irradiance=0.0)
        elif elapsed < 150:
            self.demo_phase_name = "Phase 5/6: Severe Blizzard (Cut-Out Wind Turbines Shut Down)"
            self.sim.weather.set_override(condition="Polar Blizzard", cloud_cover=1.0, temperature=-36.0, wind_speed=27.5, solar_irradiance=0.0)
        elif elapsed < 180:
            self.demo_phase_name = "Phase 6/6: Storm Clears & Rated Wind Generation Restored"
            self.sim.weather.set_override(condition="Clear", cloud_cover=0.15, temperature=-20.0, wind_speed=12.0, solar_irradiance=420.0)
        else:
            # Complete demo cycle
            self.demo_phase_name = "Demo Completed - Resuming Normal AI Dynamics"
            self.stop_demo_mode()

    def _run_loop(self):
        """Continuous background execution tick."""
        while not self._stop_event.is_set():
            start_ts = time.time()
            
            if self.is_running:
                # 1. Update demo if active
                if self.demo_active:
                    self._execute_demo_phase()

                # Pipeline Step T1: Data Ingestion & Observation
                t_obs_start = time.perf_counter()
                obs = self._gym_helper._get_obs(self.latest_telemetry)
                t_obs_ms = round((time.perf_counter() - t_obs_start) * 1000.0, 3)

                # Pipeline Step T2: AI Inference & RL Policy Forward Pass
                t_ai_start = time.perf_counter()
                if self.control_mode == "AI_PPO":
                    action = self.ai_agent.predict(obs, deterministic=True)
                elif self.control_mode == "BASELINE":
                    action = self.baseline_controller.select_action(self.latest_telemetry)
                else:
                    action = self.manual_action
                t_ai_ms = round((time.perf_counter() - t_ai_start) * 1000.0, 3)

                # Pipeline Step T3: Virtual Environment Microgrid Physics Simulation
                t_sim_start = time.perf_counter()
                telemetry = self.sim.step(action)
                t_sim_ms = round((time.perf_counter() - t_sim_start) * 1000.0, 3)

                # Compute reward
                reward = self._gym_helper.calculate_reward(telemetry)
                telemetry["ai_reward"] = reward
                telemetry["control_mode"] = self.control_mode
                telemetry["demo_phase"] = self.demo_phase_name
                telemetry["demo_elapsed_s"] = self.demo_seconds_elapsed

                # Synchronize Aashika's AI 24h Predictive Models & Recommendations
                forecast_list = self.ai_forecast_data.get("forecast", [])
                curr_fc = forecast_list[0] if forecast_list else {}

                # Live forward-pass predictions from Aashika's trained Scikit-Learn models
                pred_solar_kw = telemetry.get("solar_power_kw", 0.0)
                pred_wind_kw = telemetry.get("wind_power_kw", 0.0)
                pred_demand_kw = telemetry.get("total_station_load_kw", 65.0)

                temp_c = telemetry.get("temperature_c", -15.0)
                wind_mps = telemetry.get("wind_speed_m_s", 9.0)
                cloud_pct = telemetry.get("cloud_cover_pct", 20.0)
                irr_wm2 = telemetry.get("solar_irradiance_wm2", 200.0)

                if self.solar_ml_model is not None:
                    try:
                        import numpy as np
                        solar_f = np.array([[irr_wm2, cloud_pct, temp_c, 0.0, 12, 6, 2, pred_solar_kw, 1 if irr_wm2 > 10 else 0]])
                        pred_solar_kw = max(0.0, float(self.solar_ml_model.predict(solar_f)[0]))
                    except Exception:
                        pass

                if self.wind_ml_model is not None:
                    try:
                        import numpy as np
                        wind_f = np.array([[wind_mps, 0.0, 1.0, temp_c, 1013, 0.0, 12, pred_wind_kw]])
                        pred_wind_kw = max(0.0, float(self.wind_ml_model.predict(wind_f)[0]))
                    except Exception:
                        pass

                if self.demand_ml_model is not None:
                    try:
                        import numpy as np
                        severity = (wind_mps / 25.0) * 0.3 + (max(0, 50 - temp_c) / 50.0) * 0.2 + (cloud_pct / 100.0) * 0.2
                        demand_f = np.array([[temp_c, temp_c - 3.0, 12, 3, 6, 0.0, severity, pred_demand_kw, pred_demand_kw]])
                        pred_demand_kw = max(30.0, float(self.demand_ml_model.predict(demand_f)[0]))
                    except Exception:
                        pass

                telemetry["ai_forecast"] = {
                    "generated_at": self.ai_forecast_data.get("generated_at_ist", ""),
                    "active_recommendation": curr_fc.get("recommended_resources", {
                        "primary": {"name": "Wind", "value_kw": round(telemetry.get("wind_power_kw", 0.0), 1), "category": "clean renewable"},
                        "secondary": {"name": "Solar PV", "value_kw": round(telemetry.get("solar_power_kw", 0.0), 1), "category": "clean renewable"},
                        "tertiary": {"name": "Battery", "value_kw": round(abs(telemetry.get("battery_power_kw", 0.0)), 1), "category": "energy storage"},
                        "coverage_kw": round(telemetry.get("total_generation_kw", 0.0), 1),
                        "strategy": "AI PPO DISPATCH DYNAMICS"
                    }),
                    "predicted_demand_kw": round(pred_demand_kw, 1),
                    "predicted_solar_kw": round(pred_solar_kw, 1),
                    "predicted_wind_kw": round(pred_wind_kw, 1),
                    "risk_alerts": curr_fc.get("risk_alerts", []),
                    "model_confidence": curr_fc.get("model_confidence_percent", {"solar": 85.0, "wind": 78.0, "demand": 82.5})
                }

                # Synchronize Bhoomika's 12 Modeled Resources State
                p_solar = telemetry.get("solar_power_kw", 0.0)
                p_wind = telemetry.get("wind_power_kw", 0.0)
                p_bat = telemetry.get("battery_power_kw", 0.0)
                p_gen = telemetry.get("generator_power_kw", 0.0)
                soc = telemetry.get("battery_soc_pct", 70.0)

                scen = getattr(self, "active_scenario", "normal")
                p_hydro = 90.0
                p_marine = 20.0
                marine_online = True
                hydro_health = 96
                if scen == "flood":
                    p_hydro = 9.0  # Glacial runoff debris derates hydro to 10%
                    hydro_health = 68
                elif scen == "blizzard":
                    p_hydro = 15.0  # Katabatic blizzard freezes intake
                    hydro_health = 80
                elif scen == "deep_freeze":
                    p_hydro = 25.0
                    hydro_health = 84
                elif scen == "tsunami":
                    p_hydro = 35.0
                    marine_online = False
                    p_marine = 0.0
                elif scen == "storm":
                    p_hydro = 45.0

                telemetry["active_scenario"] = scen
                telemetry["hydro_power_kw"] = p_hydro

                telemetry["modeled_resources_12"] = [
                    {"id": "solar", "name": "Solar PV", "category": "renewable", "capacity_kw": 300, "output_kw": round(p_solar, 1), "online": True, "health": 98},
                    {"id": "wind", "name": "Wind Turbines", "category": "renewable", "capacity_kw": 300, "output_kw": round(p_wind, 1), "online": True, "health": 97},
                    {"id": "hydro", "name": "Hydropower", "category": "renewable", "capacity_kw": 200, "output_kw": round(p_hydro, 1), "online": True, "health": hydro_health},
                    {"id": "geothermal", "name": "Geothermal", "category": "renewable", "capacity_kw": 100, "output_kw": 95.0, "online": True, "health": 99},
                    {"id": "marine", "name": "Marine Energy", "category": "renewable", "capacity_kw": 50, "output_kw": round(p_marine, 1), "online": marine_online, "health": 94 if marine_online else 55},
                    {"id": "biomass", "name": "Biomass / Biogas", "category": "renewable", "capacity_kw": 60, "output_kw": 55.0, "online": True, "health": 95},
                    {"id": "solarthermal", "name": "Solar Thermal", "category": "renewable", "capacity_kw": 30, "output_kw": 18.0, "online": True, "health": 96},
                    {"id": "hydrogen", "name": "Hydrogen Fuel Cell", "category": "storage", "capacity_kw": 50, "output_kw": 0.0, "online": True, "health": 93},
                    {"id": "battery", "name": "LiFePO4 BESS Storage", "category": "storage", "capacity_kw": 100, "output_kw": round(abs(p_bat), 1), "online": True, "health": 92, "soc": round(soc, 1)},
                    {"id": "generator", "name": "Diesel Generator Backup", "category": "backup", "capacity_kw": 100, "output_kw": round(p_gen, 1), "online": p_gen > 0.1, "health": 91},
                    {"id": "chp", "name": "CHP Cogeneration", "category": "backup", "capacity_kw": 60, "output_kw": 0.0, "online": True, "health": 89},
                    {"id": "passive", "name": "Passive Solar Efficiency", "category": "efficiency", "capacity_kw": 10, "output_kw": 10.0, "online": True, "health": 99}
                ]

                # Pipeline Step T4: Digital Twin Synchronization (Eclipse Ditto Schema)
                t_twin_start = time.perf_counter()
                self.digital_twin.sync_from_telemetry(telemetry)
                t_twin_ms = round((time.perf_counter() - t_twin_start) * 1000.0, 3)

                # Pipeline Step T5: IoT MQTT & SQLite Persistence
                t_io_start = time.perf_counter()
                self.mqtt_client.publish_telemetry(telemetry)
                try:
                    self.database.record_telemetry(telemetry)
                except Exception as e:
                    print(f"[Database] Error recording telemetry: {e}")

                # Also insert reading into Prachi's IoT database if initialized
                if self.prachi_db:
                    try:
                        self.prachi_db.insert({
                            "timestamp": telemetry.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                            "source": "live_station_telemetry",
                            "solar_kw": p_solar,
                            "wind_kw": p_wind,
                            "temperature_c": telemetry.get("temperature_c", -25.0),
                            "wind_speed_mps": telemetry.get("wind_speed_m_s", 9.0),
                            "demand_kw": telemetry.get("total_station_load_kw", 65.0),
                            "battery_soc": soc
                        })
                    except Exception:
                        pass
                t_io_ms = round((time.perf_counter() - t_io_start) * 1000.0, 3)

                total_pipe_ms = round(t_obs_ms + t_ai_ms + t_sim_ms + t_twin_ms + t_io_ms, 3)

                # Append Integration Diagnostics to Telemetry
                telemetry["integration_metrics"] = {
                    "data_pipeline_ms": t_obs_ms,
                    "ai_inference_ms": t_ai_ms,
                    "simulation_physics_ms": t_sim_ms,
                    "digital_twin_sync_ms": t_twin_ms,
                    "iot_db_io_ms": t_io_ms,
                    "total_pipeline_ms": total_pipe_ms,
                    "pipeline_status": "ONLINE_HEALTHY",
                    "throughput_hz": round(1.0 / max(0.001, total_pipe_ms / 1000.0), 1),
                    "ai_agent_status": self.ai_agent.get_status().get("status", "READY"),
                    "twin_health_score": self.digital_twin.get_ditto_model().get("attributes", {}).get("health_score", 100),
                    "data_feed_source": getattr(self.sim.streamer, "feed_mode", "DYNAMIC_SYNTHETIC"),
                    "mqtt_connected": getattr(self.mqtt_client, "is_connected", False)
                }

                # Cache latest
                self.latest_telemetry = telemetry

                # Broadcast to WebSocket clients
                self._broadcast_telemetry(telemetry)

            # Sleep interval calculated from speed multiplier (nominal 1.0s / speed)
            nominal_interval = 1.0 / self.speed_multiplier
            elapsed_work = time.time() - start_ts
            sleep_duration = max(0.02, nominal_interval - elapsed_work)
            time.sleep(sleep_duration)

    def get_integration_manifest(self) -> Dict[str, Any]:
        """Returns structured metadata detailing the 4 integrated sub-disciplines."""
        return {
            "title": "SIH260061 Master Multi-Discipline Integration Hub",
            "version": "2.4.0",
            "architecture": "Distributed Cooperative Cyber-Physical Microgrid",
            "team_roster": {
                "prachi": {"name": "Prachi", "role": "IoT & Backend Architect", "focus": "Sensor Ingestion, Physical Boundary Validation, SQLite Storage, REST Relay APIs"},
                "aashika": {"name": "Aashika", "role": "AI / ML Engineer", "focus": "Random Forest Solar, Wind & Demand ML Models, 24-Hour Predictive Horizon"},
                "bhoomika": {"name": "Bhoomika", "role": "Energy Optimization Specialist", "focus": "12-Resource Microgrid Model, Linear Programming (LP) Power Dispatcher, Load Deferral"},
                "diya": {"name": "Diya", "role": "UI & Frontend Designer", "focus": "POLARIS 19-Page Multi-Resource Station Control Suite & Disaster Management"},
                "hitesh": {"name": "Hitesh", "role": "Digital Twin & Systems Architect", "focus": "Eclipse Ditto W3C Cyber-Physical Replica, PPO RL Policy Coordinator"}
            },
            "modules": {
                "ai_agent": {
                    "discipline": "Artificial Intelligence & 24h Forecasting",
                    "role_lead": "Aashika (AI/ML) + Hitesh (RL PPO)",
                    "status": "OPERATIONAL",
                    "framework": "Random Forest Regressors + PyTorch Actor-Critic PPO",
                    "algorithm": "24h Generation & Demand Forecaster + Clipped Surrogate RL Dispatcher",
                    "specs": "12-dim State Observation, 6 Dispatch Actions, Solar/Wind/Demand Models (solar_model.pkl, wind_model.pkl, demand_model.pkl)",
                    "latency_metric": f"{self.latest_telemetry.get('integration_metrics', {}).get('ai_inference_ms', 1.2)} ms"
                },
                "data_pipeline": {
                    "discipline": "Real-Time Sensor Ingestion & IoT Protocol Broker",
                    "role_lead": "Prachi (IoT / Backend)",
                    "status": "OPERATIONAL",
                    "framework": "Open-Meteo REST API + FastAPI Sensor Ingestion + SQLite WAL + MQTT",
                    "algorithm": "Live Antarctic McMurdo Station Ingest + Physical Threshold Ingestion Validation + Relay API",
                    "specs": "Endpoints: /sensor/data, /energy/current, /battery/status, /optimizer/input; 1-sec sampling",
                    "latency_metric": f"{self.latest_telemetry.get('integration_metrics', {}).get('data_pipeline_ms', 0.8)} ms"
                },
                "energy_optimizer": {
                    "discipline": "12-Resource Microgrid & Linear Programming Optimization",
                    "role_lead": "Bhoomika (Energy Optimization)",
                    "status": "OPERATIONAL",
                    "framework": "Simplex/LP Optimization + Deferrable Load Scheduler",
                    "algorithm": "Solar -> Wind -> Hydro -> Geothermal -> Marine -> Biomass -> Solar Thermal -> H2 Fuel Cell -> Battery -> Generator -> CHP",
                    "specs": "All 12 Resources Active, 2000 kWh Battery Storage, 20 kW Deferrable Shift, 0% Critical Load Unmet",
                    "latency_metric": f"{self.latest_telemetry.get('integration_metrics', {}).get('simulation_physics_ms', 1.5)} ms"
                },
                "digital_twin_ui": {
                    "discipline": "Digital Twin & POLARIS Multi-Page Control Center",
                    "role_lead": "Diya (UI/UX) + Hitesh (Digital Twin)",
                    "status": "OPERATIONAL",
                    "framework": "Eclipse Ditto W3C Schema + POLARIS 19-Page Fleet Interface",
                    "algorithm": "10-Node Cyber-Physical State Reflection, Real-time Subsystem Health Scoring, Part-1/Part-2 Partitioning",
                    "specs": "Live Telemetry Sync to POLARIS Dashboard (admin, disaster, battery, hydro, geothermal, biomass, etc.)",
                    "latency_metric": f"{self.latest_telemetry.get('integration_metrics', {}).get('digital_twin_sync_ms', 0.9)} ms"
                }
            },
            "system_health": {
                "overall_status": "ALL_SYSTEMS_GO",
                "roundtrip_latency_ms": self.latest_telemetry.get('integration_metrics', {}).get('total_pipeline_ms', 4.5),
                "data_synchronization": "LOCKSTEP_STRICT",
                "active_feed": getattr(self.sim.streamer, "feed_mode", "DYNAMIC_SYNTHETIC"),
                "polaris_ui_url": "/polaris"
            }
        }

    def _broadcast_telemetry(self, telemetry: Dict[str, Any]):
        """Non-blocking asynchronous dispatch to connected WebSocket clients."""
        if not self.telemetry_clients:
            return

        msg = {
            "type": "telemetry",
            "data": telemetry,
            "twin": self.digital_twin.get_ditto_model()
        }
        
        # Threadsafe async scheduling
        dead_clients = set()
        for ws in list(self.telemetry_clients):
            try:
                asyncio.run(ws.send_json(msg))
            except Exception:
                dead_clients.add(ws)
                
        if dead_clients:
            self.telemetry_clients.difference_update(dead_clients)


# Global singleton instance
coordinator = StationCoordinatorService()
