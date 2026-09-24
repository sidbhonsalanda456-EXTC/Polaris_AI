import math
from typing import Dict, Any

class PolarBatteryStorage:
    """
    Simulates a specialized Polar Station Battery Energy Storage System (BESS).
    Models LiFePO4 chemistry with cold-temperature thermal derating,
    internal resistance losses, and battery heating jacket dynamics.
    """
    def __init__(self, capacity_kwh: float = 200.0, max_power_kw: float = 50.0):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw
        
        # State variables
        self.soc = 0.70                 # State of Charge (0.0 to 1.0)
        self.stored_kwh = self.capacity_kwh * self.soc
        self.temperature = 12.0         # Celsius (internal insulated cell temperature)
        self.current_power_kw = 0.0     # Positive = charging, Negative = discharging
        self.cumulative_charged_kwh = 0.0
        self.cumulative_discharged_kwh = 0.0
        self.cycle_count = 12.4         # Equivalent full cycles
        self.state_of_health = 0.98     # 1.0 = brand new, drops with excessive deep cycles
        
        # Efficiencies
        self.charge_efficiency = 0.95
        self.discharge_efficiency = 0.95
        
        # Protective thresholds
        self.min_soc = 0.15
        self.max_soc = 0.98

    def update_thermal_state(self, ambient_temp: float, dt_hours: float = 1.0 / 60.0):
        """
        Updates internal battery temperature based on ambient cold,
        internal I^2*R Joule heating during high power, and insulation/heating jacket.
        """
        # Internal Joule heating from current throughput
        joule_heat_kw = 0.03 * (abs(self.current_power_kw) ** 1.3)
        
        # Heat transfer through insulated enclosure to outside polar cold
        insulation_r_val = 0.08  # Enclosure thermal conductance
        heat_loss_to_ambient = insulation_r_val * (self.temperature - ambient_temp)
        
        # Automatic thermal management system (heats cells if below 5°C)
        heater_power_kw = 0.0
        if self.temperature < 5.0:
            heater_power_kw = 2.5  # station battery jacket heater
            
        temp_delta = (joule_heat_kw + heater_power_kw - heat_loss_to_ambient) * (dt_hours * 8.0)
        self.temperature = max(-15.0, min(35.0, self.temperature + temp_delta))
        self.temperature = round(self.temperature, 2)

    def get_effective_power_limit(self) -> float:
        """Derates maximum battery power when cells are severely cold (< 0°C)."""
        if self.temperature < -10.0:
            return self.max_power_kw * 0.35  # Extreme cold derating
        elif self.temperature < 0.0:
            return self.max_power_kw * 0.70
        elif self.temperature > 30.0:
            return self.max_power_kw * 0.85  # Overheating derating
        return self.max_power_kw

    def charge(self, requested_power_kw: float, dt_hours: float = 1.0 / 60.0) -> float:
        """
        Charges the battery with given power up to maximum allowable rate and SOC.
        Returns actual power absorbed (kW).
        """
        effective_limit = self.get_effective_power_limit()
        charge_power = max(0.0, min(requested_power_kw, effective_limit))
        
        # Check headroom to max_soc
        max_charge_kwh = max(0.0, (self.max_soc * self.capacity_kwh) - self.stored_kwh)
        possible_charge_kwh = charge_power * dt_hours * self.charge_efficiency
        
        if possible_charge_kwh > max_charge_kwh and max_charge_kwh > 0:
            actual_kwh = max_charge_kwh
            actual_power = actual_kwh / (dt_hours * self.charge_efficiency)
        elif max_charge_kwh <= 0:
            actual_kwh = 0.0
            actual_power = 0.0
        else:
            actual_kwh = possible_charge_kwh
            actual_power = charge_power
            
        self.stored_kwh += actual_kwh
        self.soc = round(self.stored_kwh / self.capacity_kwh, 4)
        self.current_power_kw = round(actual_power, 2)
        self.cumulative_charged_kwh += actual_kwh
        self.cycle_count += (actual_kwh / (2.0 * self.capacity_kwh))
        return actual_power

    def discharge(self, requested_power_kw: float, dt_hours: float = 1.0 / 60.0) -> float:
        """
        Discharges the battery up to available capacity down to min_soc.
        Returns actual power delivered to station bus (kW).
        """
        effective_limit = self.get_effective_power_limit()
        discharge_power = max(0.0, min(requested_power_kw, effective_limit))
        
        # Check usable energy above min_soc
        usable_kwh = max(0.0, self.stored_kwh - (self.min_soc * self.capacity_kwh))
        energy_needed_kwh = (discharge_power * dt_hours) / self.discharge_efficiency
        
        if energy_needed_kwh > usable_kwh and usable_kwh > 0:
            energy_drawn_kwh = usable_kwh
            actual_power = (energy_drawn_kwh * self.discharge_efficiency) / dt_hours
        elif usable_kwh <= 0:
            energy_drawn_kwh = 0.0
            actual_power = 0.0
        else:
            energy_drawn_kwh = energy_needed_kwh
            actual_power = discharge_power
            
        self.stored_kwh -= energy_drawn_kwh
        self.soc = round(self.stored_kwh / self.capacity_kwh, 4)
        self.current_power_kw = -round(actual_power, 2)
        self.cumulative_discharged_kwh += (actual_power * dt_hours)
        self.cycle_count += (energy_drawn_kwh / (2.0 * self.capacity_kwh))
        
        # Slight degradation penalty if operating near deep discharge
        if self.soc < 0.20:
            self.state_of_health = max(0.80, self.state_of_health - 0.00002)
            
        return actual_power

    def set_soc(self, soc_pct: float):
        """Allows direct external/admin calibration of battery SOC."""
        clamped_soc = max(0.0, min(100.0, float(soc_pct))) / 100.0
        self.soc = round(clamped_soc, 4)
        self.stored_kwh = round(self.capacity_kwh * self.soc, 2)

    def maintain(self):
        """Sets power throughput to zero (standby)."""
        self.current_power_kw = 0.0

    def get_state(self) -> Dict[str, Any]:
        if self.current_power_kw > 0.05:
            status = "CHARGING"
        elif self.current_power_kw < -0.05:
            status = "DISCHARGING"
        else:
            status = "STANDBY"

        return {
            "capacity_kwh": self.capacity_kwh,
            "stored_kwh": round(self.stored_kwh, 2),
            "soc": round(self.soc * 100.0, 1),
            "status": status,
            "temperature_c": self.temperature,
            "power_kw": self.current_power_kw,
            "state_of_health_pct": round(self.state_of_health * 100.0, 1),
            "cycle_count": round(self.cycle_count, 2),
            "effective_limit_kw": round(self.get_effective_power_limit(), 1)
        }
