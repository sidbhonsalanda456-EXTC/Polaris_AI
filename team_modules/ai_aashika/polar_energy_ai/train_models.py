import os
import json
import numpy as np
import pandas as pd
from preprocess import load_data, preprocess, get_feature_sets
from solar_model import train_solar_model
from wind_model import train_wind_model
from demand_model import train_demand_model

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
METRICS_PATH = os.path.join(BASE_DIR, "output", "model_metrics.json")


def train_all():
    print("Loading and preprocessing data...")
    df = load_data()
    df = preprocess(df)
    print(f"Dataset: {len(df)} records")

    solar_f, wind_f, demand_f = get_feature_sets()

    print("\nTraining Solar Model...")
    solar_model, solar_metrics, _, _, _ = train_solar_model(df, solar_f)
    print(f"  Solar R2 (test): {solar_metrics['test']['r2']}")

    print("\nTraining Wind Model...")
    wind_model, wind_metrics, _, _, _ = train_wind_model(df, wind_f)
    print(f"  Wind R2 (test): {wind_metrics['test']['r2']}")

    print("\nTraining Demand Model...")
    demand_model, demand_metrics, _, _, _ = train_demand_model(df, demand_f)
    print(f"  Demand R2 (test): {demand_metrics['test']['r2']}")

    all_metrics = {
        "solar": solar_metrics,
        "wind": wind_metrics,
        "demand": demand_metrics,
    }

    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    with open(METRICS_PATH, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"\nAll models trained. Metrics saved to {METRICS_PATH}")
    return all_metrics


if __name__ == "__main__":
    train_all()
