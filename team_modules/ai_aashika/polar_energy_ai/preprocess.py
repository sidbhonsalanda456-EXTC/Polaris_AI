import os
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "historical_weather_energy.csv")


def load_data():
    if os.path.exists(DATA_PATH):
        return pd.read_csv(DATA_PATH)
    from history_store import load_history, to_training_dataframe
    df = to_training_dataframe(load_history())
    if df is None or df.empty:
        raise FileNotFoundError(
            "No training data found. Run run_all.py once to create the AI history archive.")
    return df


def get_season(month):
    if month in [12, 1, 2]:
        return "summer"
    elif month in [3, 4, 5]:
        return "autumn"
    elif month in [6, 7, 8]:
        return "winter"
    else:
        return "spring"


def preprocess(df):
    df = df.copy()

    if "timestamp_ist" in df.columns:
        df["timestamp_ist"] = (
            pd.to_datetime(df["timestamp_ist"], format="ISO8601", utc=True)
            .dt.tz_convert(IST))

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())

    df["hour"] = df["timestamp_ist"].dt.hour
    df["day_of_week"] = df["timestamp_ist"].dt.dayofweek
    df["month"] = df["timestamp_ist"].dt.month
    df["season"] = df["month"].apply(get_season)
    df["season_encoded"] = df["season"].map({"summer": 0, "autumn": 1, "winter": 2, "spring": 3})

    df["wind_direction_sin"] = np.sin(np.radians(df["wind_direction_deg"]))
    df["wind_direction_cos"] = np.cos(np.radians(df["wind_direction_deg"]))

    df["weather_severity_score"] = (
        (df["wind_speed_mps"] / 25).clip(0, 1) * 0.3 +
        (df["snowfall_mm"] / 10).clip(0, 1) * 0.3 +
        ((50 - df["temperature_c"]) / 50).clip(0, 1) * 0.2 +
        (df["cloud_cover_pct"] / 100).clip(0, 1) * 0.2
    )

    df["previous_hour_solar"] = df["solar_actual_kw"].shift(1).fillna(0)
    df["previous_hour_wind"] = df["wind_actual_kw"].shift(1).fillna(0)
    df["previous_hour_demand"] = df["demand_actual_kw"].shift(1).fillna(0)
    df["rolling_average_demand"] = df["demand_actual_kw"].rolling(window=24, min_periods=1).mean()
    df["rolling_average_wind"] = df["wind_actual_kw"].rolling(window=24, min_periods=1).mean()

    df["is_solar_active"] = ((df["hour"] >= 8) & (df["hour"] <= 16)).astype(int)

    return df


def get_feature_sets():
    solar_features = [
        "solar_irradiance_wm2", "cloud_cover_pct", "temperature_c", "snowfall_mm",
        "hour", "month", "season_encoded", "previous_hour_solar", "is_solar_active"
    ]
    wind_features = [
        "wind_speed_mps", "wind_direction_sin", "wind_direction_cos",
        "temperature_c", "pressure_hpa", "snowfall_mm", "hour",
        "previous_hour_wind"
    ]
    demand_features = [
        "temperature_c", "feels_like_c", "hour", "day_of_week", "month",
        "snowfall_mm", "weather_severity_score", "previous_hour_demand",
        "rolling_average_demand"
    ]
    return solar_features, wind_features, demand_features


def split_data(df, features, target, test_size=0.2):
    X = df[features].values
    y = df[target].values
    split_idx = int(len(df) * (1 - test_size))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    return X_train, X_test, y_train, y_test


if __name__ == "__main__":
    df = load_data()
    df = preprocess(df)
    solar_f, wind_f, demand_f = get_feature_sets()
    print(f"Preprocessed {len(df)} records")
    print(f"Solar features: {solar_f}")
    print(f"Wind features: {wind_f}")
    print(f"Demand features: {demand_f}")
    print(f"Columns: {list(df.columns)}")
