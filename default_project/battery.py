class Battery:
    def __init__(self, capacity_kwh=200, soc_percent=70, soh_percent=80,
                 min_soc_percent=20, max_soc_percent=100,
                 max_charge_kw=100, max_discharge_kw=100):
        self.capacity_kwh = capacity_kwh
        self.soc_percent = soc_percent
        self.soh_percent = soh_percent
        self.min_soc_percent = min_soc_percent
        self.max_soc_percent = max_soc_percent
        self.max_charge_kw = max_charge_kw
        self.max_discharge_kw = max_discharge_kw

    @property
    def effective_capacity_kwh(self):
        return self.capacity_kwh * self.soh_percent / 100

    @property
    def stored_energy_kwh(self):
        return self.effective_capacity_kwh * self.soc_percent / 100

    @property
    def min_energy_kwh(self):
        return self.effective_capacity_kwh * self.min_soc_percent / 100

    @property
    def max_energy_kwh(self):
        return self.effective_capacity_kwh * self.max_soc_percent / 100

    @property
    def available_discharge_kwh(self):
        return max(0, self.stored_energy_kwh - self.min_energy_kwh)

    @property
    def available_charge_kwh(self):
        return max(0, self.max_energy_kwh - self.stored_energy_kwh)

    @property
    def status(self):
        if self.soc_percent <= self.min_soc_percent:
            return "EMPTY"
        elif self.soc_percent >= self.max_soc_percent:
            return "FULL"
        return "READY"

    def discharge(self, energy_kwh):
        if energy_kwh <= 0:
            return 0
        actual = min(energy_kwh, self.available_discharge_kwh)
        if actual <= 0:
            return 0
        self.soc_percent -= (actual / self.effective_capacity_kwh) * 100
        self.soc_percent = round(self.soc_percent, 2)
        return actual

    def charge(self, energy_kwh):
        if energy_kwh <= 0:
            return 0
        actual = min(energy_kwh, self.available_charge_kwh)
        if actual <= 0:
            return 0
        self.soc_percent += (actual / self.effective_capacity_kwh) * 100
        self.soc_percent = round(self.soc_percent, 2)
        return actual

    def __repr__(self):
        return (f"Battery(SOC={self.soc_percent}%, SOH={self.soh_percent}%, "
                f"Stored={self.stored_energy_kwh:.1f}kWh, "
                f"Available={self.available_discharge_kwh:.1f}kWh)")
