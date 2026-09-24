import math
from typing import Dict, Any

# ==============================================================================
# PART 1: RENEWABLE ENERGY RESOURCES
# ==============================================================================

class SolarSystem:
    """
    Part 1.1: Bifacial Polar Solar Photovoltaic Array (60 kW nominal).
    Accounts for solar irradiance, albedo snow/ice reflection gain,
    and positive efficiency coefficient in Arctic/Antarctic cold.
    """
    def __init__(self, nominal_capacity_kw: float = 60.0):
        self.resource_type = "RENEWABLE"
        self.name = "Bifacial Polar PV Array"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.snow_albedo_gain = 1.20  # +20% ground reflection
        self.temp_coefficient = 0.004  # +0.4% per °C below 25°C
        self.current_output_kw = 0.0

    def calculate_output(self, irradiance_w_m2: float, ambient_temp_c: float) -> float:
        if irradiance_w_m2 <= 1.0:
            self.current_output_kw = 0.0
            return 0.0
        
        irradiance_ratio = min(1.0, (irradiance_w_m2 * self.snow_albedo_gain) / 1000.0)
        temp_factor = 1.0 + (25.0 - ambient_temp_c) * self.temp_coefficient
        temp_factor = max(0.8, min(1.25, temp_factor))
        
        power = self.nominal_capacity_kw * irradiance_ratio * temp_factor
        self.current_output_kw = round(max(0.0, power), 2)
        return self.current_output_kw


class WindSystem:
    """
    Part 1.2: Dual Arctic Wind Turbines (2 x 35 kW = 70 kW nominal).
    Aerodynamic power curve with cut-in, rated, and blizzard cut-out protection.
    """
    def __init__(self, nominal_capacity_kw: float = 70.0):
        self.resource_type = "RENEWABLE"
        self.name = "Arctic Wind Turbines"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.cut_in_speed = 3.0   # m/s
        self.rated_speed = 12.0   # m/s
        self.cut_out_speed = 25.0 # m/s storm shutdown
        self.current_output_kw = 0.0
        self.is_cut_out = False

    def calculate_output(self, wind_speed_m_s: float) -> float:
        v = max(0.0, wind_speed_m_s)
        if v < self.cut_in_speed or v >= self.cut_out_speed:
            self.is_cut_out = (v >= self.cut_out_speed)
            self.current_output_kw = 0.0
            return 0.0
        else:
            self.is_cut_out = False
            if v >= self.rated_speed:
                self.current_output_kw = self.nominal_capacity_kw
            else:
                ratio = (v - self.cut_in_speed) / (self.rated_speed - self.cut_in_speed)
                self.current_output_kw = round(self.nominal_capacity_kw * (ratio ** 3), 2)
            return self.current_output_kw


class HydroSystem:
    """
    Part 1.3: Run-of-River / Glacial Melt Hydro Generator (90 kW nominal).
    Base continuous generation with seasonal melt factor.
    """
    def __init__(self, nominal_capacity_kw: float = 90.0):
        self.resource_type = "RENEWABLE"
        self.name = "Glacial Hydro Generator"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.current_output_kw = nominal_capacity_kw

    def calculate_output(self, ambient_temp_c: float = -15.0) -> float:
        # Reduced flow in extreme freeze (-30C), steady melt flow above -10C
        flow_factor = 1.0 if ambient_temp_c > -10.0 else max(0.60, 1.0 + (ambient_temp_c + 10.0) * 0.015)
        self.current_output_kw = round(self.nominal_capacity_kw * flow_factor, 2)
        return self.current_output_kw


class GeothermalSystem:
    """
    Part 1.4: Polar Deep-Borehole Geothermal Wellhead (95 kW nominal).
    Ultra-stable continuous baseload thermal/electric generation.
    """
    def __init__(self, nominal_capacity_kw: float = 95.0):
        self.resource_type = "RENEWABLE"
        self.name = "Deep Borehole Geothermal"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.current_output_kw = nominal_capacity_kw

    def calculate_output(self) -> float:
        self.current_output_kw = self.nominal_capacity_kw
        return self.current_output_kw


class MarineSystem:
    """
    Part 1.5: Polar Coastal Tidal & Wave Array (20 kW nominal).
    Driven by tidal currents and sub-ice ocean flows.
    """
    def __init__(self, nominal_capacity_kw: float = 20.0):
        self.resource_type = "RENEWABLE"
        self.name = "Coastal Tidal/Marine Energy"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.current_output_kw = nominal_capacity_kw

    def calculate_output(self) -> float:
        self.current_output_kw = self.nominal_capacity_kw
        return self.current_output_kw


class BiomassSystem:
    """
    Part 1.6: Station Organic Waste Gasification & Biogas Digester (55 kW nominal).
    Controlled continuous clean thermal-electric output.
    """
    def __init__(self, nominal_capacity_kw: float = 55.0):
        self.resource_type = "RENEWABLE"
        self.name = "Biomass / Biogas Unit"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.current_output_kw = nominal_capacity_kw

    def calculate_output(self) -> float:
        self.current_output_kw = self.nominal_capacity_kw
        return self.current_output_kw


class SolarThermalSystem:
    """
    Part 1.7: Evacuated Tube Solar Thermal Array (18 kW nominal).
    Direct solar-to-thermal hydronic heating collector.
    """
    def __init__(self, nominal_capacity_kw: float = 18.0):
        self.resource_type = "RENEWABLE"
        self.name = "Solar Thermal Collectors"
        self.nominal_capacity_kw = nominal_capacity_kw
        self.current_output_kw = 0.0

    def calculate_output(self, irradiance_w_m2: float) -> float:
        if irradiance_w_m2 <= 5.0:
            self.current_output_kw = 0.0
            return 0.0
        ratio = min(1.0, irradiance_w_m2 / 1000.0)
        self.current_output_kw = round(self.nominal_capacity_kw * ratio, 2)
        return self.current_output_kw


class RenewableSubsystem:
    """
    Part 1 Manager: Aggregates all Renewable Energy Resources.
    Solar (60 kW) + Wind (70 kW) + Hydro (90 kW) + Geothermal (95 kW) + 
    Marine (20 kW) + Biomass (55 kW) + Solar Thermal (18 kW) = 408 kW Fleet.
    """
    def __init__(self):
        self.solar = SolarSystem(nominal_capacity_kw=60.0)
        self.wind = WindSystem(nominal_capacity_kw=70.0)
        self.hydro = HydroSystem(nominal_capacity_kw=90.0)
        self.geothermal = GeothermalSystem(nominal_capacity_kw=95.0)
        self.marine = MarineSystem(nominal_capacity_kw=20.0)
        self.biomass = BiomassSystem(nominal_capacity_kw=55.0)
        self.solar_thermal = SolarThermalSystem(nominal_capacity_kw=18.0)
        
        # Primary intermittent clean capacity (Solar + Wind = 130 kW)
        self.primary_clean_capacity_kw = 130.0
        # Total renewable fleet capacity (408 kW)
        self.total_clean_capacity_kw = 408.0

    def compute_generation(self, irradiance_w_m2: float, wind_speed_m_s: float, ambient_temp_c: float, include_fleet: bool = False) -> Dict[str, Any]:
        solar_kw = self.solar.calculate_output(irradiance_w_m2, ambient_temp_c)
        wind_kw = self.wind.calculate_output(wind_speed_m_s)
        hydro_kw = self.hydro.calculate_output(ambient_temp_c)
        geo_kw = self.geothermal.calculate_output()
        marine_kw = self.marine.calculate_output()
        biomass_kw = self.biomass.calculate_output()
        st_kw = self.solar_thermal.calculate_output(irradiance_w_m2)
        
        # Total generation: standard mode computes solar + wind (130kW nominal), fleet mode sums all
        if include_fleet:
            total_renewable_kw = round(solar_kw + wind_kw + hydro_kw + geo_kw + marine_kw + biomass_kw + st_kw, 2)
            cap_kw = self.total_clean_capacity_kw
        else:
            total_renewable_kw = round(solar_kw + wind_kw, 2)
            cap_kw = self.primary_clean_capacity_kw
        
        return {
            "solar_power_kw": solar_kw,
            "wind_power_kw": wind_kw,
            "hydro_power_kw": hydro_kw,
            "geothermal_power_kw": geo_kw,
            "marine_power_kw": marine_kw,
            "biomass_power_kw": biomass_kw,
            "solar_thermal_power_kw": st_kw,
            "total_renewable_kw": total_renewable_kw,
            "all_renewables_total_kw": round(solar_kw + wind_kw + hydro_kw + geo_kw + marine_kw + biomass_kw + st_kw, 2),
            "capacity_kw": cap_kw,
            "capacity_factor_pct": round((total_renewable_kw / max(1.0, cap_kw)) * 100.0, 1),
            "wind_blades_feathered": self.wind.is_cut_out
        }


# ==============================================================================
# PART 2: NON-RENEWABLE ENERGY RESOURCES
# ==============================================================================

class BackupDieselGenerator:
    """
    Part 2.1: Primary Emergency Polar Diesel Generator (50 kW).
    High-reliability diesel genset for life-support defense.
    Fuel rate: 0.28 L per kWh.
    """
    def __init__(self, capacity_kw: float = 50.0):
        self.resource_type = "NON_RENEWABLE"
        self.name = "Primary Diesel Generator"
        self.capacity_kw = capacity_kw
        self.is_active = False
        self.current_output_kw = 0.0
        self.fuel_consumption_rate_l_per_kwh = 0.28
        self.fuel_burned_liters = 0.0
        self.runtime_minutes = 0

    def set_output(self, requested_kw: float, dt_hours: float = 1.0 / 60.0) -> float:
        if requested_kw > 0.5:
            self.is_active = True
            self.current_output_kw = round(min(requested_kw, self.capacity_kw), 2)
            energy_kwh = self.current_output_kw * dt_hours
            self.fuel_burned_liters += round(energy_kwh * self.fuel_consumption_rate_l_per_kwh, 4)
            self.runtime_minutes += int(dt_hours * 60)
        else:
            self.is_active = False
            self.current_output_kw = 0.0
        return self.current_output_kw

    def shutdown(self):
        self.is_active = False
        self.current_output_kw = 0.0


class AuxiliaryFuelGenerator:
    """
    Part 2.2: Secondary Auxiliary Thermal/Fuel Backup Generator (25 kW).
    Fired during extreme multi-day polar blizzards when primary reserves are constrained.
    Fuel rate: 0.32 L per kWh.
    """
    def __init__(self, capacity_kw: float = 25.0):
        self.resource_type = "NON_RENEWABLE"
        self.name = "Auxiliary Thermal Fuel Generator"
        self.capacity_kw = capacity_kw
        self.is_active = False
        self.current_output_kw = 0.0
        self.fuel_consumption_rate_l_per_kwh = 0.32
        self.fuel_burned_liters = 0.0
        self.runtime_minutes = 0

    def set_output(self, requested_kw: float, dt_hours: float = 1.0 / 60.0) -> float:
        if requested_kw > 0.5:
            self.is_active = True
            self.current_output_kw = round(min(requested_kw, self.capacity_kw), 2)
            energy_kwh = self.current_output_kw * dt_hours
            self.fuel_burned_liters += round(energy_kwh * self.fuel_consumption_rate_l_per_kwh, 4)
            self.runtime_minutes += int(dt_hours * 60)
        else:
            self.is_active = False
            self.current_output_kw = 0.0
        return self.current_output_kw

    def shutdown(self):
        self.is_active = False
        self.current_output_kw = 0.0


class NonRenewableSubsystem:
    """
    Part 2 Manager: Aggregates all Non-Renewable (Fossil Fuel) Energy Resources.
    Tracks fuel reserves, burn rates, direct fuel costs, and carbon emissions.
    """
    def __init__(self, initial_fuel_reserves_liters: float = 12000.0):
        self.primary_diesel = BackupDieselGenerator(capacity_kw=50.0)
        self.aux_generator = AuxiliaryFuelGenerator(capacity_kw=25.0)
        self.total_fossil_capacity_kw = 75.0
        
        # Tank and emissions parameters
        self.initial_reserves_liters = initial_fuel_reserves_liters
        self.remaining_fuel_liters = initial_fuel_reserves_liters
        self.diesel_price_usd_per_liter = 2.45  # Airlifted polar fuel cost
        self.co2_emissions_kg_per_liter = 2.68   # Standard diesel combustion factor

    def dispatch(self, requested_kw: float, dt_hours: float = 1.0 / 60.0) -> Dict[str, Any]:
        """Dispatches non-renewable generators to cover remaining deficit."""
        req = max(0.0, requested_kw)
        
        # Primary diesel handles first 50 kW
        primary_kw = self.primary_diesel.set_output(min(req, 50.0), dt_hours)
        remaining_req = max(0.0, req - primary_kw)
        
        # Secondary aux generator handles next 25 kW if needed
        aux_kw = self.aux_generator.set_output(min(remaining_req, 25.0), dt_hours)
        
        total_fossil_kw = round(primary_kw + aux_kw, 2)
        total_fuel_burned = self.primary_diesel.fuel_burned_liters + self.aux_generator.fuel_burned_liters
        self.remaining_fuel_liters = max(0.0, self.initial_reserves_liters - total_fuel_burned)
        
        # Current burn rate in L/h
        instantaneous_burn_rate_l_h = round(
            (primary_kw * self.primary_diesel.fuel_consumption_rate_l_per_kwh) +
            (aux_kw * self.aux_generator.fuel_consumption_rate_l_per_kwh), 2
        )
        
        total_co2_kg = round(total_fuel_burned * self.co2_emissions_kg_per_liter, 2)
        total_cost_usd = round(total_fuel_burned * self.diesel_price_usd_per_liter, 2)

        return {
            "primary_diesel_kw": primary_kw,
            "aux_generator_kw": aux_kw,
            "total_non_renewable_kw": total_fossil_kw,
            "capacity_kw": self.total_fossil_capacity_kw,
            "is_active": (total_fossil_kw > 0.5),
            "fuel_burn_rate_l_h": instantaneous_burn_rate_l_h,
            "total_fuel_consumed_liters": round(total_fuel_burned, 2),
            "remaining_fuel_liters": round(self.remaining_fuel_liters, 2),
            "reserve_tank_pct": round((self.remaining_fuel_liters / self.initial_reserves_liters) * 100.0, 1),
            "carbon_emissions_kg_co2": total_co2_kg,
            "fuel_cost_usd": total_cost_usd
        }

    def shutdown_all(self):
        self.primary_diesel.shutdown()
        self.aux_generator.shutdown()


# ==============================================================================
# STATION LOADS
# ==============================================================================

class StationLoadModel:
    """
    Hierarchical polar research station electrical demand.
    Critical Loads (Life support, servers, comms) vs. Flexible Loads (scientific labs).
    """
    def __init__(self):
        self.base_life_support_kw = 18.0
        self.base_comms_kw = 6.0
        self.base_servers_kw = 10.0
        self.base_critical_lighting_kw = 4.0
        self.base_heating_kw = 16.0
        self.base_research_lab_kw = 12.0
        self.base_aux_heating_kw = 8.0
        self.base_workshop_kw = 5.0
        self.shedding_ratio = 0.0

    def calculate_loads(self, ambient_temp_c: float, shedding_ratio: float = 0.0) -> Dict[str, float]:
        self.shedding_ratio = max(0.0, min(1.0, shedding_ratio))
        critical_fixed = (self.base_life_support_kw + 
                          self.base_comms_kw + 
                          self.base_servers_kw + 
                          self.base_critical_lighting_kw)
        
        # Heating demand increases in extreme polar cold
        temp_deficit = max(0.0, -15.0 - ambient_temp_c)
        dynamic_heating = self.base_heating_kw + (temp_deficit * 0.65)
        
        critical_heating = dynamic_heating * 0.70
        aux_heating = dynamic_heating * 0.30
        
        total_critical = round(critical_fixed + critical_heating, 2)
        nominal_flexible = self.base_research_lab_kw + aux_heating + self.base_workshop_kw
        actual_flexible = round(nominal_flexible * (1.0 - self.shedding_ratio), 2)
        total_load = round(total_critical + actual_flexible, 2)
        
        return {
            "critical_load_kw": total_critical,
            "non_critical_load_kw": actual_flexible,
            "flexible_load_kw": actual_flexible,
            "nominal_flexible_kw": round(nominal_flexible, 2),
            "shed_amount_kw": round(nominal_flexible * self.shedding_ratio, 2),
            "shedding_ratio": round(self.shedding_ratio, 2),
            "heating_load_kw": round(dynamic_heating, 2),
            "total_load_kw": total_load
        }
