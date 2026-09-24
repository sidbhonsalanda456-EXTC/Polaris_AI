class Load:
    def __init__(self, name, power_kw, is_critical, deferrable=False):
        self.name = name
        self.power_kw = power_kw
        self.is_critical = is_critical
        self.deferrable = deferrable


class StationLoads:
    def __init__(self):
        self.critical_loads = [
            Load("Heating", 40, True),
            Load("Communication", 10, True),
            Load("Medical", 5, True),
        ]
        self.noncritical_loads = [
            Load("Laboratory", 25, False),
            Load("WaterHeating", 20, False, deferrable=True),
        ]

    @property
    def critical_total_kw(self):
        return sum(l.power_kw for l in self.critical_loads)

    @property
    def noncritical_total_kw(self):
        return sum(l.power_kw for l in self.noncritical_loads)

    @property
    def total_demand_kw(self):
        return self.critical_total_kw + self.noncritical_total_kw

    @property
    def deferrable_total_kw(self):
        return sum(l.power_kw for l in self.noncritical_loads if l.deferrable)

    def get_load(self, name):
        for l in self.critical_loads + self.noncritical_loads:
            if l.name == name:
                return l
        return None

    def __repr__(self):
        return (f"StationLoads(Critical={self.critical_total_kw}kW "
                f"NonCritical={self.noncritical_total_kw}kW "
                f"Total={self.total_demand_kw}kW Deferrable={self.deferrable_total_kw}kW)")
