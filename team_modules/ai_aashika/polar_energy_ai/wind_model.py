import os
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "wind_model.pkl")


def train_wind_model(df, features):
    X = df[features].values
    y = df["wind_actual_kw"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    model = RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_split=5,
        min_samples_leaf=2, random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    metrics = {
        "train": {
            "mae": round(float(mean_absolute_error(y_train, y_pred_train)), 2),
            "rmse": round(float(np.sqrt(mean_squared_error(y_train, y_pred_train))), 2),
            "r2": round(float(r2_score(y_train, y_pred_train)), 4),
        },
        "test": {
            "mae": round(float(mean_absolute_error(y_test, y_pred_test)), 2),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, y_pred_test))), 2),
            "r2": round(float(r2_score(y_test, y_pred_test)), 4),
        },
        "feature_importance": {
            feat: round(float(imp), 4)
            for feat, imp in zip(features, model.feature_importances_)
        },
    }

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    return model, metrics, X_test, y_test, y_pred_test


def load_wind_model():
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return None


def predict_wind(model, features_array):
    predictions = model.predict(features_array)
    return np.clip(predictions, 0, 300)


if __name__ == "__main__":
    from preprocess import load_data, preprocess, get_feature_sets
    df = load_data()
    df = preprocess(df)
    _, wind_f, _ = get_feature_sets()
    model, metrics, X_test, y_test, y_pred = train_wind_model(df, wind_f)
    print("Wind model trained!")
    print(json.dumps(metrics, indent=2))
