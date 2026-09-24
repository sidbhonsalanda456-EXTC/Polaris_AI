import math


class Resource:
    def __init__(self, name, category, status, capacity_kw=0.0, storage_kwh=0.0,
                 fuel_rate_l_per_kwh=0.0, note=""):
        self.name = name
        self.category = category
        self.status = status
        self.capacity_kw = capacity_kw
        self.storage_kwh = storage_kwh
        self.fuel_rate_l_per_kwh = fuel_rate_l_per_kwh
        self.note = note

    def __repr__(self):
        return f"Resource({self.name}, {self.category}, {self.status})"


CATEGORY_LABELS = {
    "renewable": "Renewable generation",
    "storage": "Storage",
    "backup": "Non-renewable / backup",
    "efficiency": "Energy-saving / efficiency",
}

RESOURCES = [
    Resource("Solar PV", "renewable", "modeled", capacity_kw=300),
    Resource("Wind", "renewable", "modeled", capacity_kw=300),
    Resource("Hydropower", "renewable", "modeled", capacity_kw=200),
    Resource("Geothermal", "renewable", "modeled", capacity_kw=100),
    Resource("Marine Energy - tidal/wave/ocean current", "renewable", "modeled", capacity_kw=50),
    Resource("Biomass/Biogas", "renewable", "modeled", capacity_kw=60),
    Resource("Solar Thermal", "renewable", "modeled", capacity_kw=30),
    Resource("Battery Energy Storage", "storage", "modeled",
             capacity_kw=100, storage_kwh=2000),
    Resource("Hydrogen Storage + Fuel Cell", "storage", "modeled",
             capacity_kw=50, storage_kwh=200),
    Resource("Diesel/Fuel Generator", "backup", "modeled", capacity_kw=100,
             fuel_rate_l_per_kwh=0.25),
    Resource("CHP/Cogeneration", "backup", "modeled", capacity_kw=60,
             fuel_rate_l_per_kwh=0.12),
    Resource("Passive Solar / Building Efficiency", "efficiency", "modeled",
             note="reduces station demand by ~10%"),
]

MODELED_RESOURCES = [r for r in RESOURCES]
PRIMARY_RENEWABLE = ["Solar PV", "Wind", "Hydropower"]
EXTRA_RENEWABLE = ["Geothermal", "Marine Energy - tidal/wave/ocean current",
                   "Biomass/Biogas", "Solar Thermal"]


def extra_renewable_kw(hour=0):
    return 0.0


def hydro_output(hour, capacity_kw=200, base_factor=0.45):
    variation = 0.75 + 0.25 * math.sin(2 * math.pi * (hour - 8) / 24)
    return capacity_kw * base_factor * variation


def geothermal_output(hour, capacity_kw=100):
    variation = 0.95 + 0.05 * math.sin(2 * math.pi * (hour - 6) / 24)
    return capacity_kw * variation


def marine_output(hour, capacity_kw=50):
    tidal = 0.5 + 0.45 * math.sin(2 * math.pi * (hour - 4) / 12.42)
    wave = 0.10 * math.sin(2 * math.pi * (hour - 2) / 24)
    return max(0.0, capacity_kw * (tidal + wave))


def biomass_output(hour, capacity_kw=60, base_factor=0.7):
    factor = base_factor + 0.15 * math.sin(2 * math.pi * (hour - 18) / 24)
    return max(0.0, capacity_kw * factor)


def solar_thermal_output(hour, capacity_kw=30):
    h = int(hour)
    if h < 9 or h > 16:
        return 0.0
    if h in (9, 16):
        return capacity_kw * 0.5
    if h in (10, 15):
        return capacity_kw * 0.8
    return capacity_kw


def hydrogen_fc_kw(hour=0, capacity_kw=50):
    return capacity_kw


PASSIVE_SOLAR_REDUCTION = 0.10


def print_resource_inventory():
    print("=" * 62)
    print("POLAR STATION ENERGY RESOURCE INVENTORY")
    print("=" * 62)
    current_category = None
    for r in RESOURCES:
        if r.category != current_category:
            current_category = r.category
            print(f"\n{current_category.upper()}")
            print("-" * 62)
        capacity = f"{r.capacity_kw:g} kW" if r.capacity_kw else ""
        storage = f" / {r.storage_kwh:g} kWh storage" if r.storage_kwh else ""
        fuel = f" / {r.fuel_rate_l_per_kwh} L/kWh" if r.fuel_rate_l_per_kwh else ""
        detail = (capacity + storage + fuel).strip()
        if r.note:
            detail = (detail + " " + r.note).strip()
        print(f"  [MODELED ] {r.name:<45} {detail}")
    print("-" * 62)
    print("  AI models: Solar + Wind + Hydro + Geothermal + Marine +")
    print("  Biogas + Solar Thermal + Demand  (all 12 resources active)")
    print("=" * 62)