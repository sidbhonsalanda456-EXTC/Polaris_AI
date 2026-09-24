"""Pydantic models for sensor data and API payloads.

These schemas define the single source of truth for data exchanged between the
IoT/backend layer, the AI module, the optimizer, and the UI.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    """One raw sensor reading (second-level)."""
    timestamp: str
    temperature_c: float
    humidity_pct: float
    wind_speed_mps: float
    wind_direction_deg: float
    solar_irradiance_wm2: float
    solar_status: str
    wind_status: str
    solar_generation_kw: float
    wind_generation_kw: float
    energy_demand_kw: float
    battery_soc_pct: Optional[float] = None
    generator_status: Optional[str] = None


class SensorBatch(BaseModel):
    """A batch of readings posted by sensors / ingestion pipeline."""
    readings: List[SensorReading]


class IngestResponse(BaseModel):
    received: int
    accepted: int
    rejected: int
    stored_total: int


class StationStatus(BaseModel):
    online: bool
    total_readings: int
    buffer_size: int
    database: str
    last_timestamp: Optional[str] = None


class EnergyCurrent(BaseModel):
    timestamp: str
    solar_generation_kw: float
    wind_generation_kw: float
    renewable_generation_kw: float
    energy_demand_kw: float
    deficit_kw: float


class BatteryStatus(BaseModel):
    timestamp: str
    soc_percent: float
    charging: bool
    capacity_kwh: float
    status: str


class OptimizerInput(BaseModel):
    """Payload the backend forwards to Bhoomi's optimizer."""
    timestamp: Optional[str] = None
    horizon: str = "1 hour"
    predicted_demand_kw: float
    predicted_solar_kw: float
    predicted_wind_kw: float
    renewable_generation_kw: float
    predicted_deficit_kw: float
    solar_status: str
    wind_status: str
    available_resources: List[str]
    recommendation: str


class OptimizerResult(BaseModel):
    """Response returned by the optimizer, stored and relayed to the UI."""
    timestamp: str
    strategy: str
    battery_charge_kw: float
    battery_discharge_kw: float
    generator_kw: float
    load_shed_kw: float
    notes: str
