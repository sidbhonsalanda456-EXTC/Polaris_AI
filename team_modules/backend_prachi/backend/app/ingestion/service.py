"""Collect -> validate -> store pipeline for incoming sensor data."""
import random
from datetime import datetime, timedelta

from ..schemas import SensorReading, SensorBatch
from ..validation.validator import validate_reading, InvalidReadingError
from ..storage.database import Database


class IngestionService:
    def __init__(self, db: Database):
        self.db = db
        self.stats = {"accepted": 0, "rejected": 0}

    def accept_batch(self, batch: SensorBatch) -> dict:
        accepted = 0
        rejected = 0
        for reading in batch.readings:
            issues = validate_reading(reading)
            if issues:
                rejected += 1
                print(f"[ingest] rejected: {issues}")
                continue
            try:
                self.db.insert_one(reading.dict())
                accepted += 1
            except Exception as e:
                rejected += 1
                print(f"[ingest] storage error: {e}")
        self.stats["accepted"] += accepted
        self.stats["rejected"] += rejected
        return {"accepted": accepted, "rejected": rejected}

    def accept_one(self, reading: SensorReading) -> dict:
        return self.accept_batch(SensorBatch(readings=[reading]))


class SensorSimulator:
    """Simulates a live sensor feed so the pipeline can be demonstrated."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.current = datetime.utcnow().replace(microsecond=0)

    def next(self) -> SensorReading:
        self.current += timedelta(seconds=1)
        hour = self.current.hour + self.current.minute / 60.0
        curve = 900.0 * max(0.0, 1 - ((hour - 12) / 6) ** 2)
        solar_status = "ONLINE" if self.rng.random() > 0.03 else "OFFLINE"
        wind_status = "ONLINE" if self.rng.random() > 0.03 else "OFFLINE"
        temp = max(-40, min(20, 12 - 25 * abs(1 - (hour / 24) * 2) + self.rng.uniform(-2, 2)))
        wind_speed = max(0.0, 12 + 8 * (self.rng.random() - 0.5))
        return SensorReading(
            timestamp=self.current.strftime("%Y-%m-%d %H:%M:%S"),
            temperature_c=round(temp, 2),
            humidity_pct=round(self.rng.uniform(40, 90), 1),
            wind_speed_mps=round(wind_speed, 2),
            wind_direction_deg=round(self.rng.uniform(0, 360), 1),
            solar_irradiance_wm2=round(curve, 1),
            solar_status=solar_status,
            wind_status=wind_status,
            solar_generation_kw=round(curve / 100 if solar_status == "ONLINE" else 0, 3),
            wind_generation_kw=round(wind_speed * 7 if wind_status == "ONLINE" else 0, 3),
            energy_demand_kw=round(200 + 60 * abs(1 - (hour / 24) * 2) + self.rng.uniform(-10, 10), 2),
            battery_soc_pct=70 + int(self.rng.uniform(-5, 5)),
            generator_status="AVAILABLE" if self.rng.random() > 0.1 else "UNAVAILABLE",
        )
