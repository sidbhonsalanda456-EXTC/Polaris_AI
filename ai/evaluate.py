from typing import Dict, Any
from simulation.station import PolarStationSimulation
from ai.environment import PolarStationEnv
from ai.baseline import BaselineHeuristicController
from ai.model import PolarAIAgent

def run_comparative_evaluation(steps: int = 144, seed: int = 42) -> Dict[str, Any]:
    """
    Executes an identical polar weather scenario across both:
    1. Baseline Heuristic Controller (non-predictive standard logic)
    2. AI PPO Controller (reinforcement learning optimization)
    Returns comparative KPIs proving AI improvement.
    """
    # 1. Evaluate Baseline
    baseline_env = PolarStationEnv(max_episode_steps=steps, seed=seed)
    baseline_controller = BaselineHeuristicController()
    obs, info = baseline_env.reset(seed=seed)
    
    baseline_total_reward = 0.0
    baseline_telemetry_history = []
    
    for _ in range(steps):
        current_telemetry = info["telemetry"]
        action = baseline_controller.select_action(current_telemetry)
        obs, reward, terminated, truncated, info = baseline_env.step(action)
        baseline_total_reward += reward
        baseline_telemetry_history.append(info["telemetry"])
        if terminated or truncated:
            break
            
    b_final = baseline_telemetry_history[-1]["summary"]
    
    # 2. Evaluate AI Agent
    ai_agent = PolarAIAgent()
    ai_env = PolarStationEnv(max_episode_steps=steps, seed=seed)
    obs, info = ai_env.reset(seed=seed)
    
    ai_total_reward = 0.0
    ai_telemetry_history = []
    
    for _ in range(steps):
        action = ai_agent.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = ai_env.step(action)
        ai_total_reward += reward
        ai_telemetry_history.append(info["telemetry"])
        if terminated or truncated:
            break
            
    a_final = ai_telemetry_history[-1]["summary"]
    
    # Calculate differentials
    fuel_saved_liters = max(0.0, round(b_final["fuel_consumed_liters"] - a_final["fuel_consumed_liters"], 2))
    diesel_kwh_avoided = max(0.0, round(b_final["total_diesel_kwh"] - a_final["total_diesel_kwh"], 2))
    
    b_renew_pct = round((b_final["total_renewable_kwh"] / max(0.1, b_final["total_energy_generated_kwh"])) * 100.0, 1)
    a_renew_pct = round((a_final["total_renewable_kwh"] / max(0.1, a_final["total_energy_generated_kwh"])) * 100.0, 1)
    
    return {
        "evaluation_steps": steps,
        "seed": seed,
        "baseline": {
            "controller_name": "Heuristic Rule-Based",
            "total_reward": round(baseline_total_reward, 2),
            "total_consumed_kwh": b_final["total_energy_consumed_kwh"],
            "renewable_kwh": b_final["total_renewable_kwh"],
            "diesel_kwh": b_final["total_diesel_kwh"],
            "fuel_consumed_liters": b_final["fuel_consumed_liters"],
            "renewable_percentage": b_renew_pct,
            "critical_availability_pct": b_final["critical_availability_pct"],
            "power_shortages": b_final["critical_shortage_events"],
            "min_soc_pct": b_final["min_battery_soc"]
        },
        "ai_controller": {
            "controller_name": "PPO Reinforcement Learning",
            "total_reward": round(ai_total_reward, 2),
            "total_consumed_kwh": a_final["total_energy_consumed_kwh"],
            "renewable_kwh": a_final["total_renewable_kwh"],
            "diesel_kwh": a_final["total_diesel_kwh"],
            "fuel_consumed_liters": a_final["fuel_consumed_liters"],
            "renewable_percentage": a_renew_pct,
            "critical_availability_pct": a_final["critical_availability_pct"],
            "power_shortages": a_final["critical_shortage_events"],
            "min_soc_pct": a_final["min_battery_soc"]
        },
        "improvement": {
            "reward_gain": round(ai_total_reward - baseline_total_reward, 2),
            "diesel_fuel_saved_liters": fuel_saved_liters,
            "diesel_kwh_avoided": diesel_kwh_avoided,
            "renewable_gain_pct": round(a_renew_pct - b_renew_pct, 1),
            "carbon_offset_kg_co2": round(fuel_saved_liters * 2.68, 2)  # 2.68 kg CO2 per liter diesel
        }
    }

if __name__ == "__main__":
    res = run_comparative_evaluation(steps=144)
    print("=== BASELINE VS AI COMPARISON ===")
    print("Baseline Reward:", res["baseline"]["total_reward"], "| Diesel:", res["baseline"]["fuel_consumed_liters"], "L")
    print("AI Reward:      ", res["ai_controller"]["total_reward"], "| Diesel:", res["ai_controller"]["fuel_consumed_liters"], "L")
    print("Diesel Saved:   ", res["improvement"]["diesel_fuel_saved_liters"], "L")
    print("Carbon Offset:  ", res["improvement"]["carbon_offset_kg_co2"], "kg CO2")
