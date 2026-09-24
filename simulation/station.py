import datetime
from typing import Dict, Any, List, Optional
from simulation.realtime_feed import RealTimeDataStreamer
from simulation.battery import PolarBatteryStorage
from simulation.energy import RenewableSubsystem, NonRenewableSubsystem, StationLoadModel

class PolarStationSimulation:
    """
    Dynamic Polar Research Station Simulator with:
    - Real-Time Dynamic Input Data Streamer (Live Antarctic API or Dynamic Synthetic)
    - Part 1: Renewable Energy Resources (Solar PV + Arctic Wind Turbines + Clean Battery)
    - Part 2: Non-Renewable Energy Resources (Primary Diesel Genset + Auxiliary Fuel Backup)
    """
    def __init__(self, seed: Optional[int] = None):
        self.streamer = RealTimeDataStreamer(mode="DYNAMIC_SYNTHETIC")
        self.weather = self.streamer
        self.battery = PolarBatteryStorage(capacity_kwh=200.0, max_power_kw=50.0)
        self.renewables = RenewableSubsystem()
        self.non_renewables = NonRenewableSubsystem(initial_fuel_reserves_liters=12000.0)
        self.load_model = StationLoadModel()
        
        self.step_index = 0
        self.simulated_time = datetime.datetime(2026, 7, 15, 12, 0, 0)
        self.dt_hours = 1.0 / 60.0  # 1 minute per tick
        
        self.current_action = 0
        self.action_name = "MAINTAIN"
        self.action_reason = "System balanced with normal grid equilibrium."
        self.active_alerts: List[Dict[str, Any]] = []
        
        # Cumulative KPIs
        self.total_energy_generated_kwh = 0.0
        self.total_energy_consumed_kwh = 0.0
        self.total_renewable_generated_kwh = 0.0
        self.total_diesel_generated_kwh = 0.0
        self.critical_shortage_events = 0
        self.total_steps_critical_met = 0
        self.min_battery_soc = 1.0
        self.max_battery_soc = 0.0
        self.shedding_active = False

    def reset(self, seed: Optional[int] = None):
        self.streamer = RealTimeDataStreamer(mode="DYNAMIC_SYNTHETIC")
        self.weather = self.streamer
        self.battery = PolarBatteryStorage(capacity_kwh=200.0, max_power_kw=50.0)
        self.renewables = RenewableSubsystem()
        self.non_renewables = NonRenewableSubsystem(initial_fuel_reserves_liters=12000.0)
        self.load_model = StationLoadModel()
        
        self.step_index = 0
        self.simulated_time = datetime.datetime(2026, 7, 15, 12, 0, 0)
        self.current_action = 0
        self.action_name = "MAINTAIN"
        self.action_reason = "Station initialized to nominal status."
        self.active_alerts = []
        self.total_energy_generated_kwh = 0.0
        self.total_energy_consumed_kwh = 0.0
        self.total_renewable_generated_kwh = 0.0
        self.total_diesel_generated_kwh = 0.0
        self.critical_shortage_events = 0
        self.total_steps_critical_met = 0
        self.min_battery_soc = 1.0
        self.max_battery_soc = 0.0
        self.shedding_active = False
        return self.step(0)

    def set_station(self, station_id: str) -> Dict[str, Any]:
        """Switches active NCPOR polar station in the real-time streamer."""
        meta = self.streamer.set_station(station_id)
        # Update base load target based on station spec
        if "base_load_kw" in meta:
            self.load_model.base_load_kw = meta["base_load_kw"]
        return meta

    def get_telemetry(self) -> Dict[str, Any]:
        return self.step(self.current_action)

    def step(self, action: int = 0) -> Dict[str, Any]:
        self.step_index += 1
        self.simulated_time += datetime.timedelta(minutes=1)
        self.current_action = action
        
        # 1. Ingest Real-Time Dynamic Input Data
        input_frame = self.streamer.step()
        ambient_temp = input_frame["temperature_c"]
        solar_irr = input_frame["solar_irradiance_w_m2"]
        wind_spd = input_frame["wind_speed_m_s"]
        
        # 2. Update BESS thermal state
        self.battery.update_thermal_state(ambient_temp, self.dt_hours)
        
        # 3. PART 1: Compute Renewable Generation
        renew_data = self.renewables.compute_generation(solar_irr, wind_spd, ambient_temp)
        solar_kw = renew_data["solar_power_kw"]
        wind_kw = renew_data["wind_power_kw"]
        renewable_total_kw = renew_data["total_renewable_kw"]
        
        # 4. Handle Shedding Actions
        if action == 3:
            self.shedding_active = True
        elif action == 4:
            self.shedding_active = False
            
        shed_ratio = 0.65 if self.shedding_active else 0.0
        loads = self.load_model.calculate_loads(ambient_temp, shed_ratio)
        critical_load_kw = loads["critical_load_kw"]
        flexible_load_kw = loads["flexible_load_kw"]
        non_critical_load_kw = loads.get("non_critical_load_kw", flexible_load_kw)
        total_demand_kw = round(critical_load_kw + non_critical_load_kw, 2)
        
        # 5. Net power balance before dispatch
        net_before_dispatch = round(renewable_total_kw - total_demand_kw, 2)
        
        # 6. Action Execution & Power Dispatch
        battery_power_kw = 0.0
        surplus_kw = 0.0
        deficit_kw = 0.0
        fossil_dispatch_kw = 0.0
        
        if action == 5:
            # Force non-renewable emergency generation on
            fossil_req = max(15.0, abs(min(0.0, net_before_dispatch)))
            non_renew_data = self.non_renewables.dispatch(fossil_req, self.dt_hours)
            fossil_dispatch_kw = non_renew_data["total_non_renewable_kw"]
        else:
            self.non_renewables.shutdown_all()
            non_renew_data = self.non_renewables.dispatch(0.0, self.dt_hours)
            
        effective_net = round(renewable_total_kw + fossil_dispatch_kw - total_demand_kw, 2)
        
        if effective_net >= 0:
            # Clean Surplus: Charge battery
            if action in [0, 1]:
                battery_power_kw = self.battery.charge(effective_net, self.dt_hours)
                surplus_kw = round(effective_net - battery_power_kw, 2)
            else:
                self.battery.maintain()
                surplus_kw = round(effective_net, 2)
        else:
            # Deficit: Discharge battery
            needed_kw = abs(effective_net)
            if action in [0, 2]:
                discharged_kw = self.battery.discharge(needed_kw, self.dt_hours)
                battery_power_kw = -discharged_kw
                remaining_def = needed_kw - discharged_kw
                
                # Automatic emergency generator fallback if critical load at risk
                if remaining_def > 0.5 and action != 5:
                    if remaining_def > non_critical_load_kw:
                        crit_deficit = remaining_def - non_critical_load_kw
                        non_renew_data = self.non_renewables.dispatch(crit_deficit, self.dt_hours)
                        fossil_dispatch_kw = non_renew_data["total_non_renewable_kw"]
                        remaining_def = max(0.0, remaining_def - fossil_dispatch_kw)
                deficit_kw = round(remaining_def, 2)
            else:
                self.battery.maintain()
                deficit_kw = round(needed_kw, 2)
                
        # 7. Critical Load Satisfaction & Energy Condition Determination
        total_avail_kw = round(renewable_total_kw + fossil_dispatch_kw + max(0.0, -battery_power_kw), 2)
        if total_avail_kw >= critical_load_kw:
            crit_supplied_pct = 100.0
            self.total_steps_critical_met += 1
        else:
            crit_supplied_pct = round((total_avail_kw / critical_load_kw) * 100.0, 1)
            self.critical_shortage_events += 1

        # Determine explicit system energy condition
        if deficit_kw > 0.5:
            energy_condition = "ENERGY DEFICIT"
        elif total_avail_kw < critical_load_kw or fossil_dispatch_kw > 0.5:
            energy_condition = "CRITICAL LOAD PRIORITY"
        elif self.shedding_active or loads.get("shed_amount_kw", 0.0) > 0.5:
            energy_condition = "NON-CRITICAL LOAD REDUCTION"
        else:
            energy_condition = "NORMAL"
            
        # 8. Renewable contribution percentage
        total_delivered_kw = min(total_demand_kw, total_avail_kw)
        if total_delivered_kw > 0:
            renewable_pct = min(100.0, round((renewable_total_kw / total_delivered_kw) * 100.0, 1))
        else:
            renewable_pct = 0.0
            
        # 9. Accumulate KPIs
        self.total_energy_generated_kwh += (renewable_total_kw + fossil_dispatch_kw) * self.dt_hours
        self.total_energy_consumed_kwh += (total_demand_kw - deficit_kw) * self.dt_hours
        self.total_renewable_generated_kwh += renewable_total_kw * self.dt_hours
        self.total_diesel_generated_kwh += fossil_dispatch_kw * self.dt_hours
        
        current_soc = self.battery.soc
        self.min_battery_soc = min(self.min_battery_soc, current_soc)
        self.max_battery_soc = max(self.max_battery_soc, current_soc)
        
        # 10. Alerts & Decision reasoning
        self._update_alerts(ambient_temp, wind_spd, current_soc, deficit_kw, fossil_dispatch_kw, non_renew_data["remaining_fuel_liters"])
        self._derive_action_reason(action, net_before_dispatch, current_soc, fossil_dispatch_kw)
        
        # Build telemetry
        return self._build_telemetry(
            input_frame=input_frame,
            renew_data=renew_data,
            non_renew_data=non_renew_data,
            critical_load_kw=critical_load_kw,
            non_critical_load_kw=non_critical_load_kw,
            flexible_load_kw=flexible_load_kw,
            total_demand_kw=total_demand_kw,
            battery_power_kw=battery_power_kw,
            fossil_dispatch_kw=fossil_dispatch_kw,
            surplus_kw=surplus_kw,
            deficit_kw=deficit_kw,
            crit_supplied_pct=crit_supplied_pct,
            renewable_pct=renewable_pct,
            energy_condition=energy_condition
        )

    def _derive_action_reason(self, action: int, net_kw: float, soc: float, gen_kw: float):
        action_map = {
            0: "MAINTAIN",
            1: "CHARGE BATTERY",
            2: "DISCHARGE BATTERY",
            3: "SHED FLEXIBLE LOADS",
            4: "RESTORE FLEXIBLE LOADS",
            5: "EMERGENCY GENERATOR ON"
        }
        self.action_name = action_map.get(action, "UNKNOWN")
        if action == 1:
            self.action_reason = f"Renewable surplus of {net_kw:.1f} kW; charging clean LiFePO4 battery (SOC: {soc*100:.1f}%)."
        elif action == 2:
            self.action_reason = f"Renewable deficit of {abs(net_kw):.1f} kW; deploying clean battery reserves to avoid fossil fuel burn."
        elif action == 3:
            self.action_reason = f"Low renewable generation or battery buffer ({soc*100:.1f}%); shedding non-critical laboratory loads."
        elif action == 4:
            self.action_reason = f"Renewable generation restored ({net_kw:.1f} kW); powering all scientific research experiments."
        elif action == 5:
            self.action_reason = f"Severe deficit exceeding battery threshold; engaging fossil diesel generator to protect life support."
        else:
            self.action_reason = f"Station microgrid in equilibrium. Holding battery in standby."

    def _update_alerts(self, ambient_temp: float, wind_spd: float, soc: float, deficit_kw: float, gen_kw: float, fuel_left_l: float):
        self.active_alerts = []
        now_str = self.simulated_time.strftime("%H:%M:%S")
        
        if deficit_kw > 1.0:
            self.active_alerts.append({
                "id": "CRITICAL_SHORTAGE", "severity": "danger",
                "title": "CRITICAL POWER SHORTAGE", "message": f"Power deficit of {deficit_kw:.1f} kW on critical bus!",
                "timestamp": now_str
            })
        if soc < 0.20:
            self.active_alerts.append({
                "id": "LOW_BATTERY", "severity": "danger",
                "title": "BATTERY RESERVE DEPLETED", "message": f"BESS SOC at {soc*100:.1f}% (under 20% protective floor).",
                "timestamp": now_str
            })
        if gen_kw > 1.0:
            self.active_alerts.append({
                "id": "NON_RENEWABLE_ACTIVE", "severity": "warning",
                "title": "NON-RENEWABLE GENERATOR ONLINE", "message": f"Fossil generator active delivering {gen_kw:.1f} kW. Consuming fuel.",
                "timestamp": now_str
            })
        if fuel_left_l < 2000.0:
            self.active_alerts.append({
                "id": "FUEL_RESERVE_LOW", "severity": "warning",
                "title": "DIESEL FUEL RESERVES LOW", "message": f"Station fuel reserve below 2,000 L ({fuel_left_l:.0f} L remaining).",
                "timestamp": now_str
            })
        if ambient_temp < -35.0:
            self.active_alerts.append({
                "id": "EXTREME_COLD", "severity": "warning",
                "title": "EXTREME POLAR FREEZE", "message": f"Temperature dropped to {ambient_temp:.1f}°C. Heating demand surging.",
                "timestamp": now_str
            })
        if wind_spd > 25.0:
            self.active_alerts.append({
                "id": "BLIZZARD_CUT_OUT", "severity": "warning",
                "title": "BLIZZARD WIND CUT-OUT", "message": f"Wind speeds ({wind_spd:.1f} m/s) exceed turbine limit. Turbines shut down.",
                "timestamp": now_str
            })

    def _build_telemetry(self, input_frame: Dict[str, Any], renew_data: Dict[str, Any],
                         non_renew_data: Dict[str, Any], critical_load_kw: float,
                         non_critical_load_kw: float, flexible_load_kw: float, total_demand_kw: float,
                         battery_power_kw: float, fossil_dispatch_kw: float,
                         surplus_kw: float, deficit_kw: float, crit_supplied_pct: float,
                         renewable_pct: float, energy_condition: str = "NORMAL") -> Dict[str, Any]:
        bat_state = self.battery.get_state()
        total_gen_kw = round(renew_data["total_renewable_kw"] + fossil_dispatch_kw, 2)
        power_balance = round(total_gen_kw - total_demand_kw, 2)
        net_energy_balance_kw = round(renew_data["total_renewable_kw"] - total_demand_kw, 2)
        
        # Carbon offset calculation (2.68 kg CO2 per liter diesel saved by using clean renewables)
        clean_kwh = self.total_renewable_generated_kwh
        co2_offset_kg = round(clean_kwh * 0.28 * 2.68, 2)
        
        return {
            "step": self.step_index,
            "timestamp": self.simulated_time.isoformat(),
            "sim_time_str": self.simulated_time.strftime("%Y-%m-%d %H:%M"),
            "station": input_frame.get("station", {}),
            
            # Real-Time Dynamic Input Stream
            "dynamic_input_stream": {
                "temperature_c": input_frame["temperature_c"],
                "solar_irradiance_w_m2": input_frame["solar_irradiance_w_m2"],
                "wind_speed_m_s": input_frame["wind_speed_m_s"],
                "cloud_cover": input_frame["cloud_cover"],
                "atmospheric_pressure_hpa": input_frame["atmospheric_pressure_hpa"],
                "weather_condition": input_frame["weather_condition"],
                "feed_mode": input_frame["feed_mode"],
                "feed_source_label": input_frame["feed_source_label"],
                "feed_status": input_frame["feed_status"]
            },
            
            # PART 1: RENEWABLE ENERGY RESOURCES
            "renewable_resources": {
                "solar_power_kw": renew_data["solar_power_kw"],
                "wind_power_kw": renew_data["wind_power_kw"],
                "hydro_power_kw": renew_data.get("hydro_power_kw", 90.0),
                "geothermal_power_kw": renew_data.get("geothermal_power_kw", 95.0),
                "marine_power_kw": renew_data.get("marine_power_kw", 20.0),
                "biomass_power_kw": renew_data.get("biomass_power_kw", 55.0),
                "solar_thermal_power_kw": renew_data.get("solar_thermal_power_kw", 18.0),
                "total_renewable_kw": renew_data["total_renewable_kw"],
                "capacity_kw": renew_data["capacity_kw"],
                "capacity_factor_pct": renew_data["capacity_factor_pct"],
                "renewable_share_pct": renewable_pct,
                "battery_soc_pct": bat_state["soc"],
                "battery_stored_kwh": bat_state["stored_kwh"],
                "battery_capacity_kwh": bat_state["capacity_kwh"],
                "battery_status": bat_state["status"],
                "battery_flow_kw": battery_power_kw,
                "battery_temp_c": bat_state["temperature_c"],
                "battery_health_pct": bat_state["state_of_health_pct"],
                "co2_offset_kg": co2_offset_kg
            },
            
            # PART 2: NON-RENEWABLE ENERGY RESOURCES
            "non_renewable_resources": {
                "primary_diesel_kw": non_renew_data["primary_diesel_kw"],
                "aux_generator_kw": non_renew_data["aux_generator_kw"],
                "total_non_renewable_kw": non_renew_data["total_non_renewable_kw"],
                "capacity_kw": non_renew_data["capacity_kw"],
                "is_active": non_renew_data["is_active"],
                "fuel_burn_rate_l_h": non_renew_data["fuel_burn_rate_l_h"],
                "total_fuel_consumed_liters": non_renew_data["total_fuel_consumed_liters"],
                "remaining_fuel_liters": non_renew_data["remaining_fuel_liters"],
                "reserve_tank_pct": non_renew_data["reserve_tank_pct"],
                "carbon_emissions_kg_co2": non_renew_data["carbon_emissions_kg_co2"],
                "fuel_cost_usd": non_renew_data["fuel_cost_usd"]
            },
            
            # Top-Level Legacy/Direct Bindings
            "solar_power_kw": renew_data["solar_power_kw"],
            "wind_power_kw": renew_data["wind_power_kw"],
            "hydro_power_kw": renew_data.get("hydro_power_kw", 90.0),
            "renewable_power_kw": renew_data["total_renewable_kw"],
            "generator_power_kw": fossil_dispatch_kw,
            "total_generation_kw": total_gen_kw,
            "total_station_load_kw": total_demand_kw,
            "critical_load_kw": critical_load_kw,
            "non_critical_load_kw": non_critical_load_kw,
            "flexible_load_kw": flexible_load_kw,
            "energy_condition": energy_condition,
            "heating_load_kw": self.load_model.calculate_loads(input_frame["temperature_c"])["heating_load_kw"],
            "battery_soc_pct": bat_state["soc"],
            "battery_stored_kwh": bat_state["stored_kwh"],
            "battery_capacity_kwh": bat_state["capacity_kwh"],
            "battery_status": bat_state["status"],
            "battery_power_kw": battery_power_kw,
            "battery_temperature_c": bat_state["temperature_c"],
            "power_balance_kw": power_balance,
            "net_energy_balance_kw": net_energy_balance_kw,
            "energy_surplus_kw": surplus_kw,
            "energy_deficit_kw": deficit_kw,
            "critical_load_supplied_pct": crit_supplied_pct,
            "renewable_percentage": renewable_pct,
            "temperature_c": input_frame["temperature_c"],
            "solar_irradiance_w_m2": input_frame["solar_irradiance_w_m2"],
            "wind_speed_m_s": input_frame["wind_speed_m_s"],
            "cloud_cover": input_frame["cloud_cover"],
            "weather_condition": input_frame["weather_condition"],
            "shedding_active": self.shedding_active,
            "ai_action": self.current_action,
            "ai_action_name": self.action_name,
            "ai_action_reason": self.action_reason,
            "alerts": self.active_alerts,
            "summary": {
                "total_energy_generated_kwh": round(self.total_energy_generated_kwh, 2),
                "total_energy_consumed_kwh": round(self.total_energy_consumed_kwh, 2),
                "total_renewable_kwh": round(self.total_renewable_generated_kwh, 2),
                "total_diesel_kwh": round(self.total_diesel_generated_kwh, 2),
                "fuel_consumed_liters": non_renew_data["total_fuel_consumed_liters"],
                "critical_shortage_events": self.critical_shortage_events,
                "critical_availability_pct": round(
                    (self.total_steps_critical_met / max(1, self.step_index)) * 100.0, 1
                ),
                "min_battery_soc": round(self.min_battery_soc * 100.0, 1),
                "max_battery_soc": round(self.max_battery_soc * 100.0, 1)
            }
        }
