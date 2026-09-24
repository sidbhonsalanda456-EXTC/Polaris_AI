# Prachi's Backend / IoT Layer

The **data backbone** of the polar station system. It collects sensor data,
validates it against physical limits, stores it in SQLite (the single source of
truth), and serves it through REST APIs to the AI/ML module, the optimizer and
the UI.

```
IoT sensors / simulated feed
        │  (every second)
        ▼
   POST /sensor/data   ──►  Validate (physical limits)
                                    │
                                    ▼
                              SQLite  (polar_station.db)
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
      GET /sensor/data     GET /energy/current      GET /battery/status
      (AI/ML pulls)        /station/status          /optimizer/input
                           (optimizer + UI)         /optimizer/result
```

## What it does

1. **Collect** — simulated one-second sensor feed (`/sensor/data/simulate`,
   `scripts/generate_24h.py` produces real CSV files).
2. **Validate** — each field is checked against physical ranges
   (`config/station.json` → `app/validation/validator.py`). Bad readings are
   rejected with the reason.
3. **Store** — valid readings go into SQLite
   (`backend/data/polar_station.db`) as the single source of truth.
4. **Serve** — REST endpoints expose the data to the rest of the team.

## Endpoints (Swagger at `/docs`)

| Method | Path               | Purpose                                              |
|--------|--------------------|------------------------------------------------------|
| POST   | `/sensor/data`     | Ingest a batch of validated sensor readings          |
| POST   | `/sensor/data/simulate` | Insert `n` simulated readings for the demo       |
| GET    | `/station/status`  | Health: total rows, database path, last timestamp    |
| GET    | `/energy/current`  | Latest solar/wind/renewable/demand/deficit snapshot  |
| GET    | `/battery/status`  | Latest battery SOC, charging state, capacity         |
| GET    | `/sensor/data`     | `granularity=1sec|1min|1hour` + limit/offset feed for AI/ML |
| POST   | `/optimizer/input` | Backend receives and stores the AI's recommendation  |
| POST   | `/optimizer/result`| Backend stores Bhoomi's optimizer decision           |
| GET    | `/optimizer/last`  | Most recent optimizer decision (for the UI)          |
| GET    | `/station/config`  | Station + resource configuration                      |

### Admin System

The administrator defines the station configuration and can change it live.
Every change is validated and saved to `config/station.json`.

| Method | Path                            | Purpose                                    |
|--------|---------------------------------|--------------------------------------------|
| GET    | `/admin/summary`                | Overview: station, AI models, resource counts |
| GET    | `/admin/resources`              | All 12 resources grouped by category       |
| GET    | `/admin/resources/{id}`         | One resource's config                      |
| PUT    | `/admin/resources/{id}`         | Update `enabled`/`status`/`capacity_kw`/`capacity_kwh`/`soc_percent` |
| POST   | `/admin/resources/{id}/toggle`  | Quick ONLINE/OFFLINE switch (`?online=true`) |
| PUT    | `/admin/config`                 | Update station `name` / `location`          |
| POST   | `/admin/config/reload`          | Re-read config from disk                    |

Example — take solar offline so Aashika's AI exercise its **resource failure
logic**:

```json
PUT /admin/resources/solar_pv
{ "status": "OFFLINE" }
```

## Resource Catalog (12 resources)

Only **Solar**, **Wind** and **Energy Demand** have AI models (`ai_modeled:
true`); the rest are expandable/configurable resources for the optimizer.

| Category             | Resources                                        | AI-modeled |
|----------------------|--------------------------------------------------|------------|
| Renewable generation | Solar PV, Wind, Hydropower, Geothermal, Marine, Biomass/Biogas, Solar Thermal | Solar + Wind only |
| Storage              | Battery Energy Storage, Hydrogen + Fuel Cell     | —          |
| Backup               | Diesel/Fuel Generator, CHP/Cogeneration          | —          |
| Efficiency           | Passive Solar / Building Energy Efficiency        | —          |

## Data

The datasets in `backend/data/` are **synthetic** (simulated, physically
plausible — not real Antarctic measurements):

| File                    | Granularity | Rows   | Meaning            |
|-------------------------|-------------|--------|--------------------|
| `polar_24h_1sec.csv`    | 1 second    | 86,400 | 24 hours raw feed  |
| `polar_24h_1min.csv`    | 1 minute    | 1,440  | aggregated feed    |
| `polar_24h_1hour.csv`   | 1 hour      | 24     | aggregated feed    |

Generate / reload them:

```bash
cd backend
.\.venv\Scripts\python.exe scripts\generate_24h.py   # build the 3 CSVs
.\.venv\Scripts\python.exe scripts\load_24h.py       # load 1sec feed into DB
```

## Run the API

```bash
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload    # dev with auto-reload
..\.venv\Scripts\python.exe -m uvicorn app.main:app             # plain run
```

Or double-click **`start_server.bat`** — it starts the server and keeps the
window open (the server dies if that window is closed).

Then open http://127.0.0.1:8000/docs for the interactive Swagger UI.

## Example call

```bash
curl -X POST http://127.0.0.1:8000/sensor/data/simulate -H "Content-Type: application/json" -d '{"n": 100}'
curl http://127.0.0.1:8000/energy/current
```

## Validation rules

Defined in `config/station.json` → `physical_limits`. Examples:
temperature −80…30 °C, humidity 0…100 %, wind 0…60 m/s, irradiance
0…1200 W/m², SOC 0…100 %. `solar_status`/`wind_status` must be `ONLINE` or
`OFFLINE`.

## How it serves the team

- **AI (Aashika)** — pulls time-series via `GET /sensor/data`, posts its
  recommendation via `POST /optimizer/input`.
- **Optimizer (Bhoomi)** — reads `GET /energy/current` + last
  `optimizer_input`, posts decisions via `POST /optimizer/result`.
- **UI / Digital Twin (Diya / Hitesh)** — reads `GET /station/status`,
  `GET /energy/current`, `GET /battery/status`, `GET /optimizer/last`,
  `GET /station/config`.