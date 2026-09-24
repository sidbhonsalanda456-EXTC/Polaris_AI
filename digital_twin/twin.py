import datetime
from typing import Dict, Any, List
from digital_twin.state import TwinComponent

class PolarStationDigitalTwin:
    """
    Digital Twin representation of the Polar Research Station with
    Two Explicit Energy Resource Subsystems:
    PART 1: Renewable Subsystems (Solar PV, Wind Turbines, Clean BESS)
    PART 2: Non-Renewable Subsystems (Primary Diesel, Auxiliary Fuel Backup)
    """
    def __init__(self, station_id: str = "polar.station:aurora-01"):
        self.station_id = station_id
        self.last_sync_time = datetime.datetime.now().isoformat()
        self.components: Dict[str, TwinComponent] = {}
        self._init_topology()

    def _init_topology(self):
        self.components = {
            # PART 1: RENEWABLE
            "solar_system": TwinComponent("solar_system", "Bifacial Solar PV (60kW)", "renewable", "NOMINAL", 100.0),
            "wind_system": TwinComponent("wind_system", "Arctic Wind Turbines (70kW)", "renewable", "NOMINAL", 100.0),
            "battery": TwinComponent("battery", "LiFePO4 Clean BESS (200kWh)", "renewable_storage", "NOMINAL", 98.0),
            
            # PART 2: NON-RENEWABLE
            "primary_diesel": TwinComponent("primary_diesel", "Emergency Diesel Genset (50kW)", "non_renewable", "STANDBY", 100.0),
            "aux_fuel_gen": TwinComponent("aux_fuel_gen", "Auxiliary Fuel Generator (25kW)", "non_renewable", "STANDBY", 100.0),
            
            # DEMAND & INFRASTRUCTURE
            "heating": TwinComponent("heating", "Thermal Environmental Control", "thermal", "NOMINAL", 100.0),
            "research_lab": TwinComponent("research_lab", "Spectroscopy & Deep Core Lab", "flexible_load", "NOMINAL", 100.0),
            "server_room": TwinComponent("server_room", "Mission Data & Communications Rack", "critical_load", "NOMINAL", 100.0),
            "communication_system": TwinComponent("communication_system", "SATCOM Array & VHF Beacon", "critical_load", "NOMINAL", 100.0),
            "critical_loads": TwinComponent("critical_loads", "Life Support Scrubbers & Living Pod", "critical_load", "NOMINAL", 100.0),
            "flexible_loads": TwinComponent("flexible_loads", "Auxiliary Workshop & Snow Melters", "flexible_load", "NOMINAL", 100.0)
        }

    def sync_from_telemetry(self, telemetry: Dict[str, Any]):
        self.last_sync_time = telemetry.get("timestamp", datetime.datetime.now().isoformat())
        
        # 1. PART 1: RENEWABLES
        solar_pwr = telemetry.get("solar_power_kw", 0.0)
        solar_irr = telemetry.get("solar_irradiance_w_m2", 0.0)
        self.components["solar_system"].properties = {
            "category": "RENEWABLE",
            "output_kw": solar_pwr,
            "irradiance_w_m2": solar_irr,
            "carbon_offset": "Clean Energy"
        }
        self.components["solar_system"].status = "NOMINAL" if solar_pwr > 0 else "OFFLINE"
        
        wind_pwr = telemetry.get("wind_power_kw", 0.0)
        wind_spd = telemetry.get("wind_speed_m_s", 0.0)
        self.components["wind_system"].properties = {
            "category": "RENEWABLE",
            "output_kw": wind_pwr,
            "wind_speed_m_s": wind_spd,
            "feathered_blades": wind_spd > 25.0
        }
        self.components["wind_system"].status = "WARNING" if wind_spd > 25.0 else "NOMINAL"

        soc = telemetry.get("battery_soc_pct", 70.0)
        bat_temp = telemetry.get("battery_temperature_c", 12.0)
        bat_pwr = telemetry.get("battery_power_kw", 0.0)
        self.components["battery"].properties = {
            "category": "CLEAN_STORAGE",
            "soc_pct": soc,
            "temperature_c": bat_temp,
            "flow_kw": bat_pwr,
            "mode": "CHARGING" if bat_pwr > 0.1 else ("DISCHARGING" if bat_pwr < -0.1 else "STANDBY")
        }
        self.components["battery"].status = "CRITICAL" if soc < 20.0 else ("WARNING" if soc < 35.0 else "NOMINAL")

        # 2. PART 2: NON-RENEWABLES
        non_ren = telemetry.get("non_renewable_resources", {})
        pri_kw = non_ren.get("primary_diesel_kw", 0.0)
        aux_kw = non_ren.get("aux_generator_kw", 0.0)
        fuel_rate = non_ren.get("fuel_burn_rate_l_h", 0.0)
        fuel_left = non_ren.get("remaining_fuel_liters", 12000.0)

        self.components["primary_diesel"].properties = {
            "category": "NON_RENEWABLE",
            "output_kw": pri_kw,
            "is_running": pri_kw > 0.5,
            "burn_rate_l_h": fuel_rate,
            "remaining_fuel_liters": fuel_left
        }
        self.components["primary_diesel"].status = "RUNNING" if pri_kw > 0.5 else "STANDBY"

        self.components["aux_fuel_gen"].properties = {
            "category": "NON_RENEWABLE",
            "output_kw": aux_kw,
            "is_running": aux_kw > 0.5
        }
        self.components["aux_fuel_gen"].status = "RUNNING" if aux_kw > 0.5 else "STANDBY"

        # 3. LOADS & HABITAT
        crit_met_pct = telemetry.get("critical_load_supplied_pct", 100.0)
        status_crit = "NOMINAL" if crit_met_pct >= 99.9 else "CRITICAL"
        self.components["critical_loads"].status = status_crit
        self.components["server_room"].status = status_crit
        self.components["communication_system"].status = status_crit

        is_shedding = telemetry.get("shedding_active", False)
        self.components["research_lab"].status = "DEGRADED" if is_shedding else "NOMINAL"
        self.components["flexible_loads"].status = "DEGRADED" if is_shedding else "NOMINAL"

    def get_ditto_model(self) -> Dict[str, Any]:
        overall_health = round(sum(c.health_score for c in self.components.values()) / len(self.components), 1)
        
        # Partition into two distinct parts
        renewable_features = {k: v.to_dict() for k, v in self.components.items() if v.category in ["renewable", "renewable_storage"]}
        non_renewable_features = {k: v.to_dict() for k, v in self.components.items() if v.category == "non_renewable"}
        load_features = {k: v.to_dict() for k, v in self.components.items() if v.category not in ["renewable", "renewable_storage", "non_renewable"]}

        return {
            "thingId": self.station_id,
            "policyId": "polar.station:policy",
            "lastSync": self.last_sync_time,
            "overallHealthScore": overall_health,
            "energyPartitions": {
                "part_1_renewable": {
                    "classification": "Zero-Emission Clean Resources",
                    "components": renewable_features
                },
                "part_2_non_renewable": {
                    "classification": "Fossil Combustion Backup Resources",
                    "components": non_renewable_features
                },
                "station_demand_network": {
                    "classification": "Hierarchical Polar Station Bus",
                    "components": load_features
                }
            },
            "features": {k: v.to_dict() for k, v in self.components.items()}
        }
