from typing import Dict, Any

class BaselineHeuristicController:
    """
    Conventional rule-based controller for polar stations without predictive AI.
    Strategy:
    - If surplus: Charge battery.
    - If deficit: Discharge battery without considering battery degradation or future storms.
    - If battery falls below 20% or deficit exceeds battery capacity: Immediately turn on diesel generator.
    - Never proactively sheds non-critical scientific loads to conserve battery reserves.
    """
    def __init__(self):
        self.name = "Baseline Heuristic Controller"

    def select_action(self, telemetry: Dict[str, Any]) -> int:
        renewable_kw = telemetry["renewable_power_kw"]
        total_load_kw = telemetry["total_station_load_kw"]
        soc = telemetry["battery_soc_pct"] / 100.0
        net = renewable_kw - total_load_kw
        
        if net > 2.0:
            # Surplus -> Charge battery
            return 1  # CHARGE_BATTERY
        elif net < -2.0:
            # Deficit
            if soc > 0.20:
                # Discharge battery
                return 2  # DISCHARGE_BATTERY
            else:
                # Deep battery deficit -> Turn on diesel generator
                return 5  # EMERGENCY_GENERATOR_ON
        else:
            # Balanced
            return 0  # MAINTAIN
