import os
import sys
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from backend.services.station_service import coordinator
from ai.evaluate import run_comparative_evaluation

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

router = APIRouter(prefix="/api")

# Pydantic request models
class StreamModeRequest(BaseModel):
    mode: str

class StreamInputRequest(BaseModel):
    temperature: Optional[float] = None
    solar: Optional[float] = None
    wind: Optional[float] = None
    cloud: Optional[float] = None

class SpeedRequest(BaseModel):
    speed: float

class ModeRequest(BaseModel):
    mode: str

class ActionRequest(BaseModel):
    action: int

class TrainingRequest(BaseModel):
    timesteps: Optional[int] = 2880

class WeatherOverrideRequest(BaseModel):
    condition: Optional[str] = None
    cloud_cover: Optional[float] = None
    temperature: Optional[float] = None
    wind_speed: Optional[float] = None
    solar_irradiance: Optional[float] = None

class StationSelectRequest(BaseModel):
    station: str

class ShowcaseScenarioRequest(BaseModel):
    scenario: str


@router.get("/status")
def get_status():
    return {
        "status": "success",
        "data": coordinator.latest_telemetry,
        "is_running": coordinator.is_running,
        "control_mode": coordinator.control_mode,
        "speed": coordinator.speed_multiplier,
        "demo_active": coordinator.demo_active,
        "demo_phase": coordinator.demo_phase_name,
        "active_scenario": getattr(coordinator, "active_scenario", "normal")
    }

@router.get("/forecast")
def get_ai_forecast():
    """Returns Aashika's 24-hour predictive AI model forecast, risk alerts, and recommendations."""
    return {
        "status": "success",
        "data": coordinator.ai_forecast_data,
        "live_summary": coordinator.latest_telemetry.get("ai_forecast", {})
    }

@router.get("/history")
def get_history(limit: int = 60):
    rows = coordinator.database.get_recent_telemetry(limit=limit)
    return {"status": "success", "count": len(rows), "data": rows}

@router.get("/ai")
def get_ai_status():
    status = coordinator.ai_agent.get_status()
    status.update({
        "current_action": coordinator.latest_telemetry.get("ai_action"),
        "current_action_name": coordinator.latest_telemetry.get("ai_action_name"),
        "current_reason": coordinator.latest_telemetry.get("ai_action_reason"),
        "current_reward": coordinator.latest_telemetry.get("ai_reward"),
        "control_mode": coordinator.control_mode
    })
    return {"status": "success", "data": status}

@router.get("/twin")
def get_digital_twin():
    return {"status": "success", "data": coordinator.digital_twin.get_ditto_model()}

@router.get("/alerts")
def get_alerts(limit: int = 20):
    return {
        "status": "success",
        "active_alerts": coordinator.latest_telemetry.get("alerts", []),
        "recent_alerts": coordinator.database.get_recent_alerts(limit=limit)
    }

@router.get("/summary")
def get_summary():
    telemetry = coordinator.latest_telemetry
    return {
        "status": "success",
        "summary": telemetry.get("summary", {}),
        "station_time": telemetry.get("sim_time_str"),
        "step": telemetry.get("step")
    }

@router.get("/comparison")
def get_comparison(steps: int = 144, seed: int = 42):
    results = run_comparative_evaluation(steps=steps, seed=seed)
    return {"status": "success", "data": results}

@router.get("/integration")
def get_integration():
    manifest = coordinator.get_integration_manifest()
    manifest["live_metrics"] = coordinator.latest_telemetry.get("integration_metrics", {})
    return {"status": "success", "data": manifest}

@router.get("/optimizer/latest")
def get_optimizer_latest():
    """Returns the latest 12-resource LP optimization run from Default Project."""
    out_file = os.path.join(PROJECT_ROOT, "default_project", "output", "auto_hourly_lp.json")
    if os.path.exists(out_file):
        try:
            with open(out_file, "r") as f:
                return {"status": "success", "data": json.load(f)}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "No optimization runs found"}

@router.post("/optimizer/run")
def run_default_project_optimizer(scenario: str = "auto", interval: str = "hourly", engine: str = "lp"):
    """Triggers Default Project LP optimizer on 12 polar microgrid resources."""
    dp_dir = os.path.join(PROJECT_ROOT, "default_project")
    if dp_dir not in sys.path:
        sys.path.insert(0, dp_dir)
    try:
        from default_project.api import run_station_optimization
        payload = run_station_optimization(interval=interval, scenario=scenario, engine=engine)
        return {"status": "success", "data": payload.get("summary", {})}
    except Exception as e:
        # Fallback to reading precomputed run
        out_file = os.path.join(dp_dir, "output", "auto_hourly_lp.json")
        if os.path.exists(out_file):
            with open(out_file, "r") as f:
                return {"status": "success", "data": json.load(f).get("summary", {})}
        return {"status": "error", "message": str(e)}

@router.get("/training")
def get_training_status():
    stats = coordinator.ai_trainer.get_stats()
    history = coordinator.database.get_training_history(limit=50)
    return {"status": "success", "stats": stats, "history": history}

# Simulation Controls
@router.post("/simulation/start")
def start_simulation():
    coordinator.set_running(True)
    return {"status": "success", "is_running": True}

@router.post("/simulation/stop")
def stop_simulation():
    coordinator.set_running(False)
    return {"status": "success", "is_running": False}

@router.post("/simulation/reset")
def reset_simulation():
    data = coordinator.reset_simulation()
    return {"status": "success", "message": "Simulation reset", "data": data}

@router.post("/simulation/speed")
def set_simulation_speed(req: SpeedRequest):
    coordinator.set_speed(req.speed)
    return {"status": "success", "speed": coordinator.speed_multiplier}

@router.post("/simulation/mode")
def set_simulation_mode(req: ModeRequest):
    coordinator.set_control_mode(req.mode)
    return {"status": "success", "mode": coordinator.control_mode}

@router.post("/simulation/action")
def set_manual_action(req: ActionRequest):
    coordinator.set_manual_action(req.action)
    return {"status": "success", "action": coordinator.manual_action}

@router.post("/simulation/weather")
def override_weather(req: WeatherOverrideRequest):
    coordinator.sim.weather.set_override(
        condition=req.condition,
        cloud_cover=req.cloud_cover,
        temperature=req.temperature,
        wind_speed=req.wind_speed,
        solar_irradiance=req.solar_irradiance
    )
    return {"status": "success", "message": "Weather override set"}

@router.post("/simulation/weather/clear")
def clear_weather_override():
    coordinator.sim.weather.clear_override()
    return {"status": "success", "message": "Weather override cleared"}

# Demo Mode Controls
@router.post("/demo/start")
def start_demo():
    coordinator.start_demo_mode()
    return {"status": "success", "message": "Dynamic polar demo mode started"}

@router.post("/demo/stop")
def stop_demo():
    coordinator.stop_demo_mode()
    return {"status": "success", "message": "Demo mode stopped"}

# Training Controls
@router.post("/training/start")
def start_training(req: TrainingRequest):
    def _on_update(stats):
        coordinator.database.record_training_log(stats)
        # Notify training WebSocket clients
        for client in list(coordinator.training_clients):
            try:
                import asyncio
                asyncio.run(client.send_json({"type": "training_update", "data": stats}))
            except Exception:
                pass

    res = coordinator.ai_trainer.start_training(total_timesteps=req.timesteps, on_update=_on_update)
    return {"status": "success", "result": res}

@router.post("/training/stop")
def stop_training():
    res = coordinator.ai_trainer.stop_training()
    return {"status": "success", "result": res}

@router.post("/model/load")
def load_model():
    coordinator.ai_agent.load_or_initialize()
    return {"status": "success", "message": "Model reloaded into coordinator agent"}

# Real-Time Dynamic Streamer & Two-Part Energy Endpoints
@router.get("/energy/two-part")
def get_two_part_energy():
    telemetry = coordinator.latest_telemetry
    return {
        "status": "success",
        "timestamp": telemetry.get("timestamp"),
        "part_1_renewable": telemetry.get("renewable_resources", {}),
        "part_2_non_renewable": telemetry.get("non_renewable_resources", {}),
        "dynamic_input_stream": telemetry.get("dynamic_input_stream", {}),
        "total_station_demand_kw": telemetry.get("total_station_load_kw", 0.0),
        "power_balance_kw": telemetry.get("power_balance_kw", 0.0)
    }

@router.post("/stream/mode")
def set_stream_mode(req: StreamModeRequest):
    coordinator.sim.streamer.set_mode(req.mode)
    return {
        "status": "success",
        "mode": req.mode,
        "source_label": coordinator.sim.streamer.feed_source_label
    }

@router.post("/stream/input")
def set_stream_input(req: StreamInputRequest):
    coordinator.sim.streamer.set_mode("MANUAL_STREAM")
    coordinator.sim.streamer.set_manual_inputs(
        temperature=req.temperature,
        solar=req.solar,
        wind=req.wind,
        cloud=req.cloud
    )
    return {"status": "success", "message": "Manual stream inputs applied"}

# NCPOR Research Station & Showcase Control Endpoints
@router.get("/stations")
def get_stations():
    """Returns official NCPOR polar stations catalog and active selection."""
    return {"status": "success", "data": coordinator.get_stations()}

@router.post("/stations/select")
def select_station(req: StationSelectRequest):
    """Switches active NCPOR polar station (Bharati, Maitri, Himadri)."""
    meta = coordinator.set_active_station(req.station)
    return {"status": "success", "station": meta}

@router.post("/showcase/scenario")
def trigger_showcase_scenario(req: ShowcaseScenarioRequest):
    """Triggers preset dynamic scenario for evaluators/showcase."""
    res = coordinator.apply_showcase_scenario(req.scenario)
    return {"status": "success", "data": res}


