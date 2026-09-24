import os
import torch
from typing import Optional, Dict, Any
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from ai.environment import PolarStationEnv

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "ppo_polar_agent.zip"
)

class PolarAIAgent:
    """
    Manages the PPO Reinforcement Learning policy for Polar Station Energy Management.
    Optimized for Windows with RTX 3050 GPU / CPU fallback.
    """
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model: Optional[PPO] = None
        self.is_loaded = False
        self.load_or_initialize()

    def load_or_initialize(self):
        """Attempts to load a pre-trained model from disk or initializes a fresh policy."""
        if os.path.exists(self.model_path):
            try:
                self.model = PPO.load(self.model_path, device=self.device)
                self.is_loaded = True
                print(f"[PolarAIAgent] Successfully loaded trained PPO model from {self.model_path} ({self.device})")
                return
            except Exception as e:
                print(f"[PolarAIAgent] Error loading existing model: {e}. Initializing fresh PPO policy.")
        
        # Initialize fresh model
        env = PolarStationEnv()
        self.model = PPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=3e-4,
            n_steps=144,
            batch_size=36,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            verbose=0,
            device=self.device
        )
        self.is_loaded = True
        print(f"[PolarAIAgent] Initialized fresh PPO policy on {self.device}")

    def predict(self, obs, deterministic: bool = True) -> int:
        """Generates the optimal discrete energy management action (0 to 5)."""
        if self.model is None:
            return 0
        action, _ = self.model.predict(obs, deterministic=deterministic)
        return int(action)

    def save(self, path: Optional[str] = None):
        target_path = path or self.model_path
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if self.model is not None:
            self.model.save(target_path)
            print(f"[PolarAIAgent] Model successfully saved to {target_path}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "model_path": self.model_path,
            "device": self.device,
            "is_loaded": self.is_loaded,
            "framework": "PyTorch + Stable-Baselines3 (PPO)",
            "observation_dim": 14,
            "action_dim": 6
        }
