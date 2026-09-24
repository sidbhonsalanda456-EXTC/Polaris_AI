class Generator:
    def __init__(self, min_kw=20, max_kw=100, fuel_rate_liters_per_kwh=0.25):
        self.min_kw = min_kw
        self.max_kw = max_kw
        self.fuel_rate = fuel_rate_liters_per_kwh
        self.status = "AVAILABLE"
        self.total_fuel_used_liters = 0
        self.total_energy_produced_kwh = 0

    @property
    def is_available(self):
        return self.status in ("AVAILABLE", "RUNNING")

    def produce(self, demand_kw):
        if not self.is_available:
            return 0
        output = max(self.min_kw, min(demand_kw, self.max_kw))
        self.status = "RUNNING"
        return output

    def calculate_fuel(self, energy_kwh):
        return energy_kwh * self.fuel_rate

    def record_production(self, energy_kwh):
        fuel = self.calculate_fuel(energy_kwh)
        self.total_fuel_used_liters += fuel
        self.total_energy_produced_kwh += energy_kwh
        return fuel

    def __repr__(self):
        return (f"Generator(Min={self.min_kw}kW Max={self.max_kw}kW "
                f"Fuel={self.total_fuel_used_liters:.1f}L)")
