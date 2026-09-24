import pytest
from simulation.weather import PolarWeatherModel
from simulation.battery import PolarBatteryStorage
from simulation.energy import SolarSystem, WindSystem, BackupDieselGenerator, StationLoadModel
from simulation.station import PolarStationSimulation

def test_weather_model_dynamics():
    weather = PolarWeatherModel(seed=42)
    s1 = weather.step()
    assert -45.0 <= s1["temperature"] <= 5.0
    assert 0.0 <= s1["solar_irradiance"] <= 1000.0
    assert 0.0 <= s1["wind_speed"] <= 40.0
    assert 0.0 <= s1["cloud_cover"] <= 1.0
    assert s1["condition"] in ["Clear", "Partly Cloudy", "Overcast", "High Wind", "Polar Blizzard"]

def test_weather_override():
    weather = PolarWeatherModel(seed=42)
    weather.set_override(condition="Polar Blizzard", temperature=-40.0, wind_speed=30.0)
    s = weather.step()
    assert s["condition"] == "Polar Blizzard"
    assert s["temperature"] == -40.0
    assert s["wind_speed"] == 30.0
    weather.clear_override()
    assert not weather.override_active

def test_battery_charge_discharge():
    battery = PolarBatteryStorage(capacity_kwh=200.0, max_power_kw=50.0)
    assert battery.soc == 0.70
    
    # Test charging
    absorbed = battery.charge(30.0, dt_hours=1.0/60.0)
    assert absorbed > 0.0
    assert battery.soc >= 0.70
    assert battery.current_power_kw > 0.0
    
    # Test discharging
    delivered = battery.discharge(25.0, dt_hours=1.0/60.0)
    assert delivered > 0.0
    assert battery.current_power_kw < 0.0

def test_battery_thermal_derate():
    battery = PolarBatteryStorage(capacity_kwh=200.0, max_power_kw=50.0)
    battery.temperature = -12.0
    limit = battery.get_effective_power_limit()
    assert limit < battery.max_power_kw

def test_wind_power_curve():
    wind = WindSystem(nominal_capacity_kw=70.0)
    # Below cut-in (3 m/s)
    assert wind.calculate_output(2.0) == 0.0
    # Between cut-in and rated (e.g. 7.5 m/s)
    mid_power = wind.calculate_output(7.5)
    assert 0.0 < mid_power < 70.0
    # At rated (12 m/s)
    assert wind.calculate_output(12.0) == 70.0
    # Cut-out shutdown (26 m/s)
    assert wind.calculate_output(26.0) == 0.0

def test_solar_system_generation():
    solar = SolarSystem(nominal_capacity_kw=60.0)
    # Night
    assert solar.calculate_output(0.0, -25.0) == 0.0
    # Daylight
    pwr = solar.calculate_output(600.0, -25.0)
    assert pwr > 20.0

def test_station_load_model_heating_and_shedding():
    load_model = StationLoadModel()
    normal_loads = load_model.calculate_loads(ambient_temp_c=-15.0, shedding_ratio=0.0)
    cold_loads = load_model.calculate_loads(ambient_temp_c=-35.0, shedding_ratio=0.0)
    # Deep cold must increase heating demand
    assert cold_loads["heating_load_kw"] > normal_loads["heating_load_kw"]
    assert cold_loads["total_load_kw"] > normal_loads["total_load_kw"]
    
    # Shedding must reduce flexible loads
    shed_loads = load_model.calculate_loads(ambient_temp_c=-15.0, shedding_ratio=0.6)
    assert shed_loads["flexible_load_kw"] < normal_loads["flexible_load_kw"]

def test_station_simulation_step():
    sim = PolarStationSimulation(seed=123)
    t = sim.step(action=0)
    assert "total_generation_kw" in t
    assert "total_station_load_kw" in t
    assert "battery_soc_pct" in t
    assert "power_balance_kw" in t
    assert t["critical_load_supplied_pct"] >= 0.0
