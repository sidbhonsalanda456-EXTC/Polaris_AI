import math
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Any, Tuple, Optional
from simulation.station import PolarStationSimulation

class PolarStationEnv(gym.Env):
    """
    Gymnasium-compliant reinforcement learning environment for
    Polar Research Station Energy Management (SIH260061).
    """
    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(self, max_episode_steps: int = 144, seed: Optional[int] = None):
        super().__init__()
        self.max_episode_steps = max_episode_steps
        self.sim = PolarStationSimulation(seed=seed)
        self.current_step = 0
        
        # 6 Discrete dispatch actions
        self.action_space = spaces.Discrete(6)
        
        # 14 continuous normalized observation features
        self.observation_space = spaces.Box(
            low=-2.0, high=2.0, shape=(14,), dtype=np.float32
        )

    def _get_obs(self, telemetry: Dict[str, Any]) -> np.ndarray:
        solar_norm = float(telemetry["solar_power_kw"] / 60.0)
        wind_norm = float(telemetry["wind_power_kw"] / 70.0)
        soc_norm = float(telemetry["battery_soc_pct"] / 100.0)
        bat_temp_norm = float((telemetry["battery_temperature_c"] - 10.0) / 25.0)
        total_load_norm = float(telemetry["total_station_load_kw"] / 100.0)
        crit_load_norm = float(telemetry["critical_load_kw"] / 50.0)
        flex_load_norm = float(telemetry["flexible_load_kw"] / 50.0)
        amb_temp_norm = float((telemetry["temperature_c"] + 25.0) / 25.0)
        cloud_norm = float(telemetry["cloud_cover"])
        wind_spd_norm = float(telemetry["wind_speed_m_s"] / 30.0)
        
        # Diurnal phase
        phase = (self.current_step % 240) / 240.0 * 2.0 * math.pi
        time_phase_norm = float(math.sin(phase))
        
        net_balance_norm = float(np.clip(telemetry["power_balance_kw"] / 50.0, -1.0, 1.0))
        gen_status_norm = 1.0 if telemetry["generator_power_kw"] > 0.5 else 0.0
        shed_status_norm = 1.0 if telemetry["shedding_active"] else 0.0
        
        obs = np.array([
            solar_norm,
            wind_norm,
            soc_norm,
            bat_temp_norm,
            total_load_norm,
            crit_load_norm,
            flex_load_norm,
            amb_temp_norm,
            cloud_norm,
            wind_spd_norm,
            time_phase_norm,
            net_balance_norm,
            gen_status_norm,
            shed_status_norm
        ], dtype=np.float32)
        
        return np.clip(obs, -2.0, 2.0)

    def calculate_reward(self, telemetry: Dict[str, Any]) -> float:
        """
        Mathematical Reward Formulation:
        R = R_critical + R_renewable + R_battery - R_diesel - R_shedding - R_deficit
        """
        # 1. Critical load satisfaction (+8.0 if 100%, heavy penalty if dropped)
        crit_met_pct = telemetry["critical_load_supplied_pct"]
        if crit_met_pct >= 99.9:
            r_critical = 8.0
        else:
            r_critical = -60.0 * ((100.0 - crit_met_pct) / 100.0)
            
        # 2. Renewable energy utilization (+4.0 scaled by fraction)
        renew_pct = telemetry["renewable_percentage"]
        r_renewable = 4.0 * (renew_pct / 100.0)
        
        # 3. Battery health & safety zone (healthy zone: 40% - 85%)
        soc = telemetry["battery_soc_pct"] / 100.0
        if 0.40 <= soc <= 0.85:
            r_battery = 2.0
        elif soc < 0.20:
            r_battery = -20.0 * ((0.20 - soc) / 0.20)  # Severe penalty for deep discharge
        elif soc < 0.40:
            r_battery = -2.0 * ((0.40 - soc) / 0.20)
        else:
            r_battery = 0.5  # Slightly high SOC, close to 100%
            
        # 4. Backup diesel generator penalty (-8.0 * load fraction)
        gen_kw = telemetry["generator_power_kw"]
        r_diesel = -8.0 * (gen_kw / 50.0)
        
        # 5. Flexible load curtailment penalty (penalize unnecessary shedding)
        r_shedding = -1.5 if telemetry["shedding_active"] else 0.0
        
        # 6. Unmet deficit penalty
        deficit_kw = telemetry["energy_deficit_kw"]
        r_deficit = -15.0 * min(1.0, deficit_kw / 25.0)
        
        total_reward = r_critical + r_renewable + r_battery + r_diesel + r_shedding + r_deficit
        return round(float(total_reward), 3)

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        self.current_step = 0
        telemetry = self.sim.reset(seed=seed)
        obs = self._get_obs(telemetry)
        return obs, {"telemetry": telemetry}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self.current_step += 1
        telemetry = self.sim.step(action)
        reward = self.calculate_reward(telemetry)
        telemetry["ai_reward"] = reward
        
        terminated = False
        # Blackout safety termination if critical load is dropped for too long
        if telemetry["critical_load_supplied_pct"] < 50.0:
            terminated = True
            
        truncated = self.current_step >= self.max_episode_steps
        obs = self._get_obs(telemetry)
        
        info = {
            "telemetry": telemetry,
            "reward": reward,
            "step": self.current_step
        }
        return obs, reward, terminated, truncated, info

    def render(self):
        pass
