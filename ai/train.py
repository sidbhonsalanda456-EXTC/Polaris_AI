import os
import time
import threading
from typing import Dict, Any, Optional, Callable
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from ai.environment import PolarStationEnv
from ai.model import DEFAULT_MODEL_PATH

class TrainingMetricsTracker(BaseCallback):
    """
    Custom Stable-Baselines3 Callback to capture real-time training statistics
    and deliver them to the dashboard / training API.
    """
    def __init__(self, total_timesteps: int, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(verbose=0)
        self.total_timesteps = total_timesteps
        self.progress_callback = progress_callback
        
        self.current_episode = 0
        self.episode_rewards = []
        self.best_reward = -float("inf")
        self.running_reward = 0.0
        self.step_counter = 0
        self.episode_reward_accum = 0.0
        self.critical_met_steps = 0
        self.renewable_accum = 0.0

    def _on_step(self) -> bool:
        self.step_counter += 1
        reward = self.locals["rewards"][0]
        self.episode_reward_accum += reward
        
        info = self.locals["infos"][0]
        telemetry = info.get("telemetry", {})
        if telemetry.get("critical_load_supplied_pct", 0) >= 99.9:
            self.critical_met_steps += 1
        self.renewable_accum += telemetry.get("renewable_percentage", 0)

        # Check if episode ended
        dones = self.locals["dones"]
        if dones[0]:
            self.current_episode += 1
            ep_reward = round(float(self.episode_reward_accum), 2)
            self.episode_rewards.append(ep_reward)
            if ep_reward > self.best_reward:
                self.best_reward = ep_reward
            
            # Rolling 20-episode average
            recent = self.episode_rewards[-20:]
            self.running_reward = round(sum(recent) / len(recent), 2)
            
            progress_pct = round(min(100.0, (self.step_counter / max(1, self.total_timesteps)) * 100.0), 1)
            crit_avail_pct = round((self.critical_met_steps / max(1, self.locals["infos"][0]["step"])) * 100.0, 1)
            avg_renewable_pct = round(self.renewable_accum / max(1, self.locals["infos"][0]["step"]), 1)
            
            stats = {
                "episode": self.current_episode,
                "current_reward": ep_reward,
                "average_reward": self.running_reward,
                "best_reward": round(float(self.best_reward), 2),
                "progress_pct": progress_pct,
                "timesteps": self.step_counter,
                "total_timesteps": self.total_timesteps,
                "critical_availability_pct": crit_avail_pct,
                "renewable_utilization_pct": avg_renewable_pct,
                "is_active": True
            }
            
            if self.progress_callback:
                self.progress_callback(stats)
                
            # Reset episode accumulators
            self.episode_reward_accum = 0.0
            self.critical_met_steps = 0
            self.renewable_accum = 0.0

        return True


class PolarAITrainer:
    """
    Manages non-blocking asynchronous training threads for PPO.
    """
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self.is_training = False
        self.train_thread: Optional[threading.Thread] = None
        self.stop_requested = False
        
        self.latest_stats: Dict[str, Any] = {
            "episode": 0,
            "current_reward": 0.0,
            "average_reward": 0.0,
            "best_reward": 0.0,
            "progress_pct": 0.0,
            "timesteps": 0,
            "total_timesteps": 0,
            "critical_availability_pct": 100.0,
            "renewable_utilization_pct": 0.0,
            "is_active": False
        }
        self.history = []

    def start_training(self, total_timesteps: int = 2880, on_update: Optional[Callable] = None):
        """Launches training in a background daemon thread."""
        if self.is_training:
            return {"status": "already_training", "message": "Training is already in progress"}

        self.stop_requested = False
        self.is_training = True
        self.latest_stats["is_active"] = True
        self.latest_stats["total_timesteps"] = total_timesteps

        def _train_worker():
            try:
                env = PolarStationEnv(max_episode_steps=144)
                
                # Check for existing weights to fine-tune
                if os.path.exists(self.model_path):
                    model = PPO.load(self.model_path, env=env)
                else:
                    model = PPO(
                        "MlpPolicy",
                        env,
                        learning_rate=3e-4,
                        n_steps=144,
                        batch_size=36,
                        n_epochs=10,
                        gamma=0.99,
                        verbose=0
                    )

                def _cb(stats):
                    self.latest_stats.update(stats)
                    self.history.append(dict(stats))
                    if on_update:
                        on_update(stats)

                callback = TrainingMetricsTracker(
                    total_timesteps=total_timesteps,
                    progress_callback=_cb
                )

                print(f"[PolarAITrainer] Started PPO training for {total_timesteps} steps...")
                model.learn(total_timesteps=total_timesteps, callback=callback)
                
                # Save trained model
                os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
                model.save(self.model_path)
                print(f"[PolarAITrainer] Training completed. Saved model to {self.model_path}")
            except Exception as e:
                print(f"[PolarAITrainer] Training error: {e}")
            finally:
                self.is_training = False
                self.latest_stats["is_active"] = False

        self.train_thread = threading.Thread(target=_train_worker, daemon=True)
        self.train_thread.start()
        return {"status": "started", "timesteps": total_timesteps}

    def stop_training(self):
        self.stop_requested = True
        self.is_training = False
        self.latest_stats["is_active"] = False
        return {"status": "stopped"}

    def get_stats(self) -> Dict[str, Any]:
        return dict(self.latest_stats)


# CLI testing utility
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=720, help="Timesteps to train")
    args = parser.parse_args()

    trainer = PolarAITrainer()
    print("Running quick training session...")
    trainer.start_training(total_timesteps=args.timesteps, on_update=lambda s: print(f"Ep {s['episode']}: Reward={s['current_reward']}, Avg={s['average_reward']}"))
    while trainer.is_training:
        time.sleep(0.5)
    print("Finished CLI training check.")
