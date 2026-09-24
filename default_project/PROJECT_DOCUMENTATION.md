# AI-Driven Smart Energy Management System for Polar Research Stations

## Project Overview
Smart energy optimization prototype for a polar research station. AI predicts renewable generation (solar + wind) and energy demand, then an optimizer decides in real time how to power the station: use renewable energy first, then battery, then the fuel generator — while automatically shifting to backup sources if any source fails.

## Team
| Member | Role | Responsibility |
|---|---|---|
| Prachi | IoT / Backend | Sensor data capture, validation, storage, APIs |
| Aashika | AI / ML | Solar, wind, and energy demand prediction models |
| Bhoomika | Energy Optimization | Battery, loads, generator, LP optimizer (this module) |
| Diya | UI | Dashboards and visualization |
| Hitesh | Digital Twin | Virtual replica of station, simulation |

**Data flow:** IoT/backend (sensor data) -> AI/ML (predictions) -> Optimizer (decides supply) -> backend (store) + UI (display) + digital twin (simulation)

## Complete System Resources
1. Solar PV
2. Wind
3. Hydropower
4. Geothermal
5. Marine energy (tidal / wave / ocean current)
6. Biomass / Biogas
7. Solar thermal
8. Battery energy storage
9. Hydrogen storage + fuel cell
10. Diesel / fuel generator
11. CHP / cogeneration
12. Passive solar / building energy efficiency

## Prototype Scope
All 12 resources are **MODELED and active** (no "coming when needed"). Forecast shapes live in `resources.py` / `forecast_24h.py`.

Modeled sources (priority order **Solar -> Wind -> Hydro -> Geothermal -> Marine -> Biomass -> Solar Thermal -> Hydrogen (fuel cell) -> Battery -> Diesel Generator -> CHP**):
- Solar PV: 300 kW capacity (predicted daytime curve)
- Wind: 300 kW capacity (power curve)
- Hydropower: 200 kW capacity (steady run-of-river profile, ~90 kW avg)
- Geothermal: 100 kW (steady, ~95 kW avg)
- Marine Energy (tidal/wave): 50 kW (tidal + wave profile)
- Biomass / Biogas: 60 kW (dispatchable, ~55 kW avg)
- Solar Thermal: 30 kW (daytime curve 09:00-16:00)
- Hydrogen Storage + Fuel Cell: 50 kW / 200 kWh storage (surplus renewable → H2, released when renewables/battery fall short)
- Battery Energy Storage: 100 kW / 2000 kWh
- Diesel/Fuel Generator: 100 kW backup (min 20 kW when running)
- CHP/Cogeneration: 60 kW backup (last resort, highest cost)
- Passive Solar / Building Efficiency: reduces station demand by 10% (included in the demand curve)

The full resource list is defined in `resources.py`; it prints the inventory at startup.

## System Specifications (used by this prototype)
### Loads (`loads.py`)
| Load | Power | Type |
|---|---|---|
| Heating | 40 kW | Critical |
| Communication | 10 kW | Critical |
| Medical | 5 kW | Critical |
| Laboratory | 25 kW | Non-critical |
| Water Heating | 20 kW | Non-critical |
| **Total** | **100 kW** | |
| **Critical total** | **55 kW** | |

### Battery (`battery.py`)
- Capacity: 2000 kWh (effective = capacity x SOH)
- SOH: 80% -> effective capacity 1600 kWh
- Start SOC: 70%
- Min SOC: 20% (safety floor, never fully drained)
- Max SOC: 100%
- Max charge / discharge power: 100 kW
- Continuous degradation cost when discharging: 0.1 / kWh (LP objective)
- Charging bonus: 0.0002/kWh credited so surplus renewable energy is stored in the battery (surplus = plus point)
- Status: EMPTY / READY / FULL; result column shows CHARGING / DISCHARGING / IDLE

### Generator (`generator.py`)
- Min output: 20 kW, Max output: 100 kW
- Fuel rate: 0.25 L/kWh
- Fuel cost: 10 / L
- Operating rule: if it runs, it must run at >= 20 kW

### Renewable forecast (`forecast_24h.py`)
- Solar capacity: 300 kW (daytime curve 08:00-16:00)
- Wind capacity: 300 kW (power curve: cut-in 3 m/s, rated 12 m/s, cut-out 25 m/s)
- Demand: 24-hour profile with daily load factor, base 100 kW

## Decision Priority
1. Solar PV
2. Wind
3. Hydropower
4. Geothermal
5. Marine energy (tidal/wave)
6. Biomass / Biogas
7. Solar thermal
8. Hydrogen fuel cell
9. Battery storage
10. Diesel fuel generator
11. CHP / cogeneration
(priority costs encoded in the LP objective: solar 0, wind 0.0005, hydro 0.001, geothermal 0.0011, marine 0.0012, biomass 0.0013, solar thermal 0.0014, H2 0.0015 per kWh; operating cost keeps diesel/H2/CHP as last-resort backups)

## Role Coverage (Energy Optimization block)
This module covers the full assigned block:
**AI Prediction -> Energy Optimization -> Energy Allocation -> Battery Management -> Load Scheduling -> Generator Management -> Final Optimal Decision**

| Requirement | Where handled |
|---|---|
| Energy balance (surplus/deficit) | `forecast_24h.py` (deficit/surplus per step) + LP balance constraint |
| Energy source priority | LP objective tiering: Solar -> Wind -> Hydro -> Battery -> Generator |
| Battery SOC / SOH | `battery.py` (SOC, SOH 80%, min 20%, charge/discharge/idle state) |
| Battery idle state | `optimizer_lp.py` result column: CHARGING / DISCHARGING / IDLE |
| Critical vs non-critical load | `loads.py` + LP hard constraint (critical always served if possible) |
| Reduce/postpone non-critical during shortage | LP sheds non-critical (unmet) |
| Load scheduling (deferrable loads) | `scheduler.py` - WaterHeating shifted into surplus (high-renewable) hours |
| Generator ON only when needed, min/max | `generator.py` + LP binary gen_on, 20-100 kW band |
| Minimize fuel | fuel cost in LP objective (2.5/kWh) |
| Final decision output | `print_optimal_decision()` - Solar/Wind/Hydro/Battery/Gen/SOC/Critical verdict |

## Load Scheduling
- WaterHeating (20 kW) is marked deferrable in `loads.py`
- `scheduler.py` removes it from low-renewable hours and schedules it into the hours with most surplus renewable energy (run water heating when solar is high)
- Shown in the LOAD SCHEDULING section of output; each hour flagged `RUN` or `off`

## LP Optimizer (`optimizer_lp.py`)
PuLP MILP solved per time step.

**Objective:** minimize
- fuel cost = 10 (per liter) x 0.25 (L/kWh) x generator output
- battery wear = 0.1 x battery discharge
- unmet-load penalty = 10,000 x unmet load
- renewable priority: solar 0, wind 0.0005/kWh, hydro 0.001/kWh (Solar -> Wind -> Hydro order)

**Variables:** solar_used, wind_used, hydro_used, ext_renew_used, batt_discharge, batt_charge, batt_mode (binary), gen_output, gen_on (binary), unmet.

**Constraints:**
- Energy balance: solar + wind + batt_discharge + gen + unmet == demand + batt_charge
- Critical load (55 kW) always served if possible
- Battery stored energy stays within [min, max]
- Generator either off or within [20, 100] kW
- No simultaneous battery charge + discharge (binary)

**Infeasible fallback:** if a scenario makes the LP impossible (e.g. generator down + battery empty at night), a safe heuristic takes over: use renewables -> drain battery to min -> run generator -> report unmet honestly. It also charges the battery from any surplus when feasible.

## Failure Detection & Automatic Shifting (AUTO MODE)
No user choice is needed - the AI forecasts supply, detects source problems automatically, and shifts to the best available source for every reading. Availability in the forecast table is plain text: **`available`** only when the source can actually produce energy right then, otherwise **`not available`** (and its output shows 0.0 kW). Examples: solar is `not available` at night (no sunlight), wind is `not available` when wind speed is below the turbine cut-in or during a maintenance window, hydro is `not available` during its maintenance window.

| Detected problem | Auto-switch behavior |
|---|---|
| Wind NOT available 02:00-03:59 | Shift to solar/hydro/battery/generator |
| Hydro NOT available 05:00-05:59 | Shift to solar/wind/battery/generator |
| Generator NOT available 21:00-22:59 | Renewable + battery only |

Solar is always available during daylight (08:00-16:00) including at noon - it only appears `not available` once there is no sunlight (nighttime).

Every shifted step logs an event (e.g. `WIND FAILURE -> shifted to best source`). A legend at the bottom of the output defines the table columns: `Met=Y` (critical loads fully satisfied that step), `24/24` (steps met / total steps), and "Auto shift events". All power columns carry `(kW)` units and all energy totals carry `kWh`, scaled correctly per step so hourly/minute/second runs all show correct energy-per-step.

## Natural Disasters: Flood / Storm / Tsunami
The 24 h forecast flags incoming natural events and derates the energy system accordingly (disaster info is shown in a **"DISASTER FORECAST"** note printed right below the forecast table - no extra table column):
- **FLOOD** (04:00-04:59) - hydro power derated to 10% (silt/debris; inland safety)
- **TSUNAMI** (08:00-08:59) - coastal sources affected: marine power off, wind derated to 15%
- **STORM** (15:00-15:59) - wind turbines pitched to 15% (safety) and solar cut to 40% (cloud cover)

Disasters are *predicted* like any supply reduction (they are not source failures, so the "shift events" counter is unaffected). Because the AI looks ahead, each disaster window triggers the pre-charge module below, and results/JSON log `DISASTER <type> -> derates + pre-charge battery` plus `emergency.disaster_warnings`.

## AI Pre-Charge Preemption (Storm/Failure Look-Ahead)
Before a predicted problem, the AI **banks energy into the battery in advance** ("intelligence" mode):
- A look-ahead window (default 4 h) scans the 24 h forecast for upcoming UNAVAILABLE windows, predicted deficits, **and floods/storms/tsunamis**.
- During that window the optimizer rewards charging (`PRE-CHARGE: failure predicted -> banking energy`) and adds a **RESERVE HOLD** - the battery refuses to discharge, saving it for the imminent failure, so short rows ride on renewables/generator instead.
- Charging is safe: it can only use surplus renewable energy (`batt_chg <= surplus`), never drops critical loads, and stops at full.
- Summary prints `AI PRE-CHARGE banked: X kWh (before predicted storm)`; JSON summary adds `ai_precharge_steps` and `ai_precharge_energy_kWh`. Tunables: `PRE_CHARGE_LOOKAHEAD_HOURS`, `PRE_CHARGE_TARGET_SOC_PCT`, `PRE_CHARGE_REWARD_PER_KWH` in `optimizer_lp.py`.

## Emergency Energy System (`emergency.py`)
Runs after every optimization and prints **NOTIFICATIONS** to the user:
- `[ALERT] <time> - WIND/HYDRO source problem detected, AI auto-switched to best available source`
- `[ALERT] <time> - GENERATOR source problem detected, AI auto-switched to renewable + battery`
- `[EMERGENCY: CRITICAL/MINOR] <time> - supply shortfall X kW` when demand cannot be served
- `[CAUTION] battery SOC below 25%` and `[INFO] generator at maximum output`
- Reports `Total unmet energy (kWh)` and, when everything is healthy, "All sources healthy. No emergency situations."

## Simulation Intervals
| Interval | Readings | Engine | Runtime |
|---|---|---|---|
| Per Hour | 24 | PuLP LP | <1 s |
| Per Minute | 1,440 | PuLP LP | ~20 s |
| Per Second | 86,400 | Fast heuristic engine (`optimizer_fast.py`) | ~5 s |

Per-second uses the fast engine because a full 86,400-step LP run is impractical (~100 min). The fast engine keeps identical output format and units.

## How to Run
```
cd C:\Users\bhoomika\polar_energy
py main.py          # fully automatic: hourly LP + minute LP + second fast engine
py optimizer_lp.py auto   # LP only, hourly, auto mode
py verify_optimizer.py    # automated checks (ALL CHECKS PASSED)
py api.py hourly auto     # JSON export CLI
```
`main.py` needs NO input - no interval menu, no scenario choice. Output: resource inventory -> initial state -> 24h forecast (with units) -> LP optimization table (kW columns, Met/SOC/Events) -> summary (kWh totals + surplus PLUS POINT + renewable share %) -> FINAL OPTIMAL DECISION -> LEGEND -> EMERGENCY notifications -> final state -> saved JSON filename.

## Project Files
| File | Purpose |
|---|---|
| `main.py` | Entry point - fully automatic run (hourly LP, minute LP, per-second fast engine) |
| `api.py` | Programmatic API + JSON export for backend/UI/digital twin |
| `battery.py` | Battery model (SOC/SOH, charge/discharge) |
| `loads.py` | Critical + non-critical load definitions |
| `generator.py` | Diesel generator model + fuel tracking |
| `forecast_24h.py` | 24h solar/wind/hydro/demand forecast, auto failure windows, kw units |
| `optimizer_lp.py` | PuLP LP optimizer, per-step solve (kW in, kWh energy units), fallback, summary, final decision, legend |
| `optimizer_fast.py` | Fast heuristic engine for per-second real-time (same output format) |
| `scheduler.py` | Deferrable load scheduling (run water heating in high-renewable hours) |
| `resources.py` | Full 12-resource catalog (modeled vs expandable) + inventory print |
| `emergency.py` | Emergency Energy System - source-failure + shortfall + low-reserve notifications |
| `verify_optimizer.py` | Automated auto-mode + invariant checks (run: `py verify_optimizer.py`) |

## Team Integration API (`api.py`)
Any team module can call the optimizer programmatically and get JSON:
```python
from api import run_station_optimization
payload = run_station_optimization(interval="hourly", scenario="auto",
                                   engine="lp",
                                   schedule_loads=True, save_json=True)
# payload contains: config, initial_state (battery SOH/SOC, loads, generator),
# forecast (solar/wind/hydro/demand/deficit/surplus), optimization_results
# (solar/wind/hydro/batt/gen used, battery state, SOC after, critical met, events),
# final_state, emergency (alerts + total unmet kWh), summary, 
# deferrable_scheduled_timestamps, saved_to
```
- `scenario="auto"` (default) detects failures automatically; pass a specific name ("solar_failure") to force a fault window
- `engine="fast"` for per-second runs (LP is slow at that scale)
- Saves to `output/<scenario>_<interval>_<engine>.json` (e.g. `output/auto_hourly_lp.json`)
- `output/` contains only JSON (no secrets), safe for Prachi's backend to consume
- CLI mode: `py api.py hourly auto`
- Combine with `resources.extra_renewable_kw()` to add expandable renewables later

## Dependencies
- Python 3 + `pulp` (`py -m pip install -r requirements.txt`)
- Only built-in modules otherwise (datetime, math, json, os)

## Verification (tested)
- AUTO MODE verified at hourly (LP), minute (LP), and per-second (fast engine) intervals
- `py verify_optimizer.py` -> **59 checks passed, 0 failed**
- All critical loads met every step, zero unmet kWh in all intervals
- Auto shift events detected automatically (5 hourly / 300 minute / 18,000 second)
- Every one of the 12 resources within its modeled capacity every step
- Emergency notifications fire for every source problem; alerts == shift events
- Battery energy conservation verified per row (SOC moves exactly with charge/discharge)
- No simultaneous battery charge/discharge; generator off when OFFLINE, capped at 100 kW
- Surplus renewable energy reported as a PLUS POINT and stored in the 2000 kWh battery
- JSON export created and re-parsed successfully

## Integrations (planned / future)
- Read predicted solar/wind/demand values from Aashika's AI model output (JSON) instead of `forecast_24h.py`
- Backend (Prachi) and UI (Diya) consume `output/*.json` from `api.py` (format already defined)
- Digital twin (Hitesh) consumes `optimization_results` energy schedules for simulation
- Add expandable resources (hydro, geothermal, marine, biomass, solar thermal, hydrogen + fuel cell, CHP) by filling in `capacity_kw` / forecast values in `resources.py` and the forecast/LP inputs (already supported: `extra_renewable_kw` column, default 0)