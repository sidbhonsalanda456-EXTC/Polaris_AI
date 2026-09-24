import pytest
import numpy as np
from ai.environment import PolarStationEnv
from ai.baseline import BaselineHeuristicController

def test_gym_environment_initialization():
    env = PolarStationEnv(max_episode_steps=50)
    assert env.action_space.n == 6
    assert env.observation_space.shape == (14,)
    
    obs, info = env.reset(seed=42)
    assert isinstance(obs, np.ndarray)
    assert obs.shape == (14,)
    assert np.all(obs >= -2.0) and np.all(obs <= 2.0)
    assert "telemetry" in info

def test_gym_environment_step():
    env = PolarStationEnv(max_episode_steps=20)
    obs, info = env.reset(seed=42)
    
    # Test valid action executions
    for act in range(6):
        obs, reward, terminated, truncated, info = env.step(act)
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (14,)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)

def test_reward_function_properties():
    env = PolarStationEnv()
    
    # Healthy nominal telemetry
    nominal_telemetry = {
        "critical_load_supplied_pct": 100.0,
        "renewable_percentage": 85.0,
        "battery_soc_pct": 75.0,
        "generator_power_kw": 0.0,
        "shedding_active": False,
        "energy_deficit_kw": 0.0
    }
    r_nominal = env.calculate_reward(nominal_telemetry)
    assert r_nominal > 5.0  # Should be strongly positive
    
    # Severe deficit & dropped critical load telemetry
    critical_drop_telemetry = {
        "critical_load_supplied_pct": 60.0,
        "renewable_percentage": 10.0,
        "battery_soc_pct": 10.0,
        "generator_power_kw": 30.0,
        "shedding_active": True,
        "energy_deficit_kw": 15.0
    }
    r_critical_drop = env.calculate_reward(critical_drop_telemetry)
    assert r_critical_drop < -10.0  # Must heavily penalize critical shortfall

def test_baseline_controller_logic():
    controller = BaselineHeuristicController()
    
    # Surplus -> should return charge action (1)
    surplus_telemetry = {
        "renewable_power_kw": 80.0,
        "total_station_load_kw": 50.0,
        "battery_soc_pct": 60.0
    }
    assert controller.select_action(surplus_telemetry) == 1
    
    # Deficit with healthy battery -> should discharge (2)
    deficit_good_battery = {
        "renewable_power_kw": 20.0,
        "total_station_load_kw": 60.0,
        "battery_soc_pct": 70.0
    }
    assert controller.select_action(deficit_good_battery) == 2
    
    # Deficit with depleted battery -> should emergency generator (5)
    deficit_low_battery = {
        "renewable_power_kw": 10.0,
        "total_station_load_kw": 60.0,
        "battery_soc_pct": 15.0
    }
    assert controller.select_action(deficit_low_battery) == 5
