"""Prachi's Backend / IoT REST API.

Endpoints (as per the team specification):
  POST /sensor/data          - ingest validated sensor readings
  GET  /station/status       - service health / counts
  GET  /energy/current       - latest energy snapshot (for optimizer + UI)
  GET  /battery/status       - latest battery status
  POST /optimizer/input      - backend relays AI predictions to Bhoomi's optimizer
  POST /optimizer/result     - backend stores the optimizer's decision for the UI

The backend is the single source of truth (SQLite). It collects -> validates ->
stores sensor data, and acts as the relay between the AI module, the optimizer
and the UI. It does NOT perform optimization itself.
"""
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends
from pydantic import ValidationError

from .schemas import (SensorBatch, IngestResponse, StationStatus,
                      EnergyCurrent, BatteryStatus, OptimizerInput,
                      OptimizerResult)
from .ingestion.service import IngestionService, SensorSimulator
from .storage.database import Database
from .config import get_config, get_resource_config
from .services.energy import current_energy, current_battery
from .admin import service as admin_service

app = FastAPI(title="Polar Station Backend / IoT Layer", version="0.1.0")
app.state.fastapi_version = "FastAPI 0.1.0"

db = Database()
ingestion = IngestionService(db)
simulator = SensorSimulator()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@app.post("/sensor/data", response_model=IngestResponse)
def ingest_sensor_data(batch: SensorBatch):
    """Accept a batch of readings, validate against physical limits, store valid ones."""
    result = ingestion.accept_batch(batch)
    return IngestResponse(
        received=len(batch.readings),
        accepted=result["accepted"],
        rejected=result["rejected"],
        stored_total=db.count(),
    )


@app.post("/sensor/data/simulate")
def ingest_simulated(n: int = 100):
    """Inject simulated sensor readings for demo purposes."""
    readings = [simulator.next() for _ in range(n)]
    batch = SensorBatch(readings=readings)
    result = ingestion.accept_batch(batch)
    return IngestResponse(
        received=len(readings), accepted=result["accepted"],
        rejected=result["rejected"], stored_total=db.count(),
    )


@app.get("/station/status", response_model=StationStatus)
def station_status():
    latest = db.latest(1)
    return StationStatus(
        online=True,
        total_readings=db.count(),
        buffer_size=0,
        database=db.db_path,
        last_timestamp=latest[0]["timestamp"] if latest else None,
    )


@app.get("/energy/current", response_model=EnergyCurrent)
def energy_current():
    return EnergyCurrent(**current_energy(db))


@app.get("/sensor/data")
def sensor_data(granularity: str = "1sec", limit: int = 100, offset: int = 0):
    """Pull stored readings for the AI/ML module and UI (time-series feed)."""
    if granularity == "1sec":
        rows = db.fetch(limit=limit, offset=offset)
    elif granularity in ("1min", "1hour"):
        rows = db.fetch_aggregated(granularity, limit=limit, offset=offset)
    else:
        raise HTTPException(status_code=400, detail="granularity must be 1sec, 1min or 1hour")
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this granularity yet.")
    return {"granularity": granularity, "count": len(rows), "data": rows}


@app.get("/battery/status", response_model=BatteryStatus)
def battery_status():
    return BatteryStatus(**current_battery(db))


@app.post("/optimizer/input")
def optimizer_input(payload: OptimizerInput):
    """Relay AI predictions to the optimizer and store the request."""
    db.insert_optimizer_input({
        **payload.dict(),
        "timestamp": payload.timestamp or _now(),
        "available_resources": ",".join(payload.available_resources),
    })
    return {"status": "received", "stored": True, "payload": payload.dict()}


@app.post("/optimizer/result")
def optimizer_result(payload: OptimizerResult):
    """Store the optimizer's decision so the UI/Digital Twin can read it."""
    db.insert_optimizer_result(payload.dict())
    return {"status": "stored", "stored": True}


@app.get("/optimizer/last")
def optimizer_last():
    """Return the most recent optimizer decision (for the UI)."""
    result = db.last_optimizer_result()
    if not result:
        raise HTTPException(status_code=404, detail="No optimizer result stored yet.")
    return result


@app.get("/station/config")
def station_config():
    """Expose station + resource configuration for the UI/backoffice."""
    return get_config()


@app.get("/health")
def health():
    return {"status": "ok", "readings": db.count()}


# ---------------------------------------------------------------------------
# Admin System — the administrator defines the station configuration
# ---------------------------------------------------------------------------

@app.get("/admin/summary")
def admin_summary():
    """Admin dashboard overview: station, AI models, resource counts."""
    return admin_service.admin_summary()


@app.get("/admin/resources")
def admin_resources():
    """All 12+ resources grouped by category, with AI-modeled flags."""
    return admin_service.list_resources()


@app.get("/admin/resources/{resource_id}")
def admin_resource(resource_id: str):
    """One resource's current configuration."""
    try:
        return admin_service.get_resource(resource_id)
    except admin_service.AdminError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/admin/resources/{resource_id}")
def admin_update_resource(resource_id: str, updates: dict):
    """Update a resource: enabled, status, capacity_kw/kwh, soc_percent.

    Example:
      {"status": "OFFLINE"}                       # take solar offline
      {"enabled": false, "status": "OFFLINE"}     # disable + offline
      {"soc_percent": 85}                         # battery SOC seen by optimizer
    """
    try:
        res = admin_service.update_resource(resource_id, updates)
        return {"updated": resource_id, "resource": res,
                "message": f"{resource_id} updated and saved to config"}
    except admin_service.AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/resources/{resource_id}/toggle")
def admin_toggle_resource(resource_id: str, online: bool = True):
    """Quick ON/OFF switch for a resource (used by admin UI buttons)."""
    try:
        res = admin_service.toggle_resource(resource_id, online)
        return {"resource": resource_id, "status": res.get("status"), "resource": res}
    except admin_service.AdminError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/admin/config")
def admin_update_station(updates: dict):
    """Update station-level config: {'name': ..., 'location': {...}}."""
    try:
        station = admin_service.update_station(updates)
        return {"updated": station}
    except admin_service.AdminError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/config/reload")
def admin_reload_config():
    """Discard in-memory changes and re-read config from disk."""
    return admin_service.reload()
