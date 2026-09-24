import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, "output", "charts")

sns.set_theme(style="darkgrid")
COLORS = {
    "solar": "#FFD700",
    "wind": "#4A90D9",
    "demand": "#FF6B6B",
    "ice_blue": "#7EC8E3",
    "navy": "#1a1a2e",
    "green": "#4CAF50",
    "orange": "#FF9800",
    "red": "#F44336",
}


def ensure_charts_dir():
    os.makedirs(CHARTS_DIR, exist_ok=True)


def plot_weather_analysis(df):
    ensure_charts_dir()
    ts = pd.to_datetime(df["timestamp_ist"])

    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)
    fig.suptitle("Weather Analysis - 48 Hour", fontsize=16, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a2e")

    for ax in axes:
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#333")

    axes[0].plot(ts, df["temperature_c"], color=COLORS["demand"], linewidth=1.5, label="Temperature")
    axes[0].set_ylabel("Temperature (°C)")
    axes[0].set_title("Temperature")
    axes[0].legend(loc="upper right", facecolor="#16213e", edgecolor="#333", labelcolor="white")

    axes[1].plot(ts, df["wind_speed_mps"], color=COLORS["wind"], linewidth=1.5, label="Wind Speed")
    axes[1].set_ylabel("Wind Speed (m/s)")
    axes[1].set_title("Wind Speed")
    axes[1].legend(loc="upper right", facecolor="#16213e", edgecolor="#333", labelcolor="white")

    axes[2].fill_between(ts, df["cloud_cover_pct"], alpha=0.3, color=COLORS["ice_blue"])
    axes[2].plot(ts, df["cloud_cover_pct"], color=COLORS["ice_blue"], linewidth=1.5, label="Cloud Cover")
    axes[2].set_ylabel("Cloud Cover (%)")
    axes[2].set_title("Cloud Cover")
    axes[2].set_ylim(0, 105)
    axes[2].legend(loc="upper right", facecolor="#16213e", edgecolor="#333", labelcolor="white")

    axes[3].fill_between(ts, df["solar_irradiance_wm2"], alpha=0.3, color=COLORS["solar"])
    axes[3].plot(ts, df["solar_irradiance_wm2"], color=COLORS["solar"], linewidth=1.5, label="Solar Irradiance")
    axes[3].set_ylabel("Solar Irradiance (W/m²)")
    axes[3].set_title("Solar Irradiance")
    axes[3].legend(loc="upper right", facecolor="#16213e", edgecolor="#333", labelcolor="white")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "weather_analysis.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_solar_prediction(y_actual, y_predicted):
    ensure_charts_dir()
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    x = range(len(y_actual))
    ax.plot(x, y_actual, color=COLORS["solar"], linewidth=1.5, label="Actual Solar", alpha=0.8)
    ax.plot(x, y_predicted, color=COLORS["demand"], linewidth=1.5, label="Predicted Solar", linestyle="--", alpha=0.8)
    ax.set_xlabel("Sample (Test Set)", color="white")
    ax.set_ylabel("Solar Output (kW)", color="white")
    ax.set_title("Solar PV: Actual vs Predicted", color="white", fontweight="bold")
    ax.legend(facecolor="#16213e", edgecolor="#333", labelcolor="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "solar_prediction.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_wind_prediction(y_actual, y_predicted):
    ensure_charts_dir()
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    x = range(len(y_actual))
    ax.plot(x, y_actual, color=COLORS["wind"], linewidth=1.5, label="Actual Wind", alpha=0.8)
    ax.plot(x, y_predicted, color=COLORS["orange"], linewidth=1.5, label="Predicted Wind", linestyle="--", alpha=0.8)
    ax.set_xlabel("Sample (Test Set)", color="white")
    ax.set_ylabel("Wind Output (kW)", color="white")
    ax.set_title("Wind Power: Actual vs Predicted", color="white", fontweight="bold")
    ax.legend(facecolor="#16213e", edgecolor="#333", labelcolor="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "wind_prediction.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_demand_prediction(y_actual, y_predicted):
    ensure_charts_dir()
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    x = range(len(y_actual))
    ax.plot(x, y_actual, color=COLORS["green"], linewidth=1.5, label="Actual Demand", alpha=0.8)
    ax.plot(x, y_predicted, color=COLORS["red"], linewidth=1.5, label="Predicted Demand", linestyle="--", alpha=0.8)
    ax.set_xlabel("Sample (Test Set)", color="white")
    ax.set_ylabel("Demand (kW)", color="white")
    ax.set_title("Station Demand: Actual vs Predicted", color="white", fontweight="bold")
    ax.legend(facecolor="#16213e", edgecolor="#333", labelcolor="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "demand_prediction.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_weather_impact(df):
    ensure_charts_dir()
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Weather Impact on Energy", fontsize=14, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a2e")

    for ax in axes:
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#333")

    axes[0].scatter(df["solar_irradiance_wm2"], df["solar_actual_kw"], alpha=0.2, s=5, color=COLORS["solar"])
    axes[0].set_xlabel("Solar Irradiance (W/m²)")
    axes[0].set_ylabel("Solar Output (kW)")
    axes[0].set_title("Irradiance vs Solar Output")

    axes[1].scatter(df["wind_speed_mps"], df["wind_actual_kw"], alpha=0.2, s=5, color=COLORS["wind"])
    axes[1].set_xlabel("Wind Speed (m/s)")
    axes[1].set_ylabel("Wind Output (kW)")
    axes[1].set_title("Wind Speed vs Wind Output")

    axes[2].scatter(df["temperature_c"], df["demand_actual_kw"], alpha=0.2, s=5, color=COLORS["demand"])
    axes[2].set_xlabel("Temperature (°C)")
    axes[2].set_ylabel("Demand (kW)")
    axes[2].set_title("Temperature vs Demand")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "weather_impact.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_resource_capacity(forecast_entry):
    ensure_charts_dir()
    resources = list(forecast_entry["predicted_generation_kw"].keys())
    capacities = []
    forecasts = []
    config_path = os.path.join(BASE_DIR, "shared", "station_config.json")
    with open(config_path) as f:
        config = json.load(f)
    res = config["resources"]

    capacity_map = {
        "solar_pv": res["solar_pv"]["capacity_kw"],
        "wind": res["wind"]["capacity_kw"],
        "hydropower": res["hydropower"]["capacity_kw"],
        "geothermal": res["geothermal"]["capacity_kw"],
        "marine_energy": res["marine_energy"]["capacity_kw"],
        "biomass_biogas": res["biomass_biogas"]["capacity_kw"],
        "solar_thermal": res["solar_thermal"]["capacity_kw"],
        "hydrogen_fuel_cell_available": res["hydrogen_fuel_cell"]["capacity_kw"],
        "battery_available": res["battery"]["effective_capacity_kwh"],
        "diesel_generator_available": res["diesel_generator"]["max_kw"],
        "chp_available": res["chp"]["capacity_kw"],
    }

    for r in resources:
        capacities.append(capacity_map.get(r, 0))
        forecasts.append(forecast_entry["predicted_generation_kw"].get(r, 0))

    labels = [r.replace("_", " ").replace("available", "").title().strip() for r in resources]

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    x = np.arange(len(labels))
    width = 0.35
    ax.bar(x - width / 2, capacities, width, label="Capacity (kW)", color=COLORS["ice_blue"], alpha=0.7)
    ax.bar(x + width / 2, forecasts, width, label="Forecast (kW)", color=COLORS["solar"], alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", color="white")
    ax.set_ylabel("Power (kW)", color="white")
    ax.set_title("Resource Capacity vs Current Forecast", color="white", fontweight="bold")
    ax.legend(facecolor="#16213e", edgecolor="#333", labelcolor="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "resource_capacity.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_renewable_vs_demand(forecast_list):
    ensure_charts_dir()
    times = []
    solar_vals = []
    wind_vals = []
    demand_vals = []

    for f in forecast_list:
        times.append(datetime.fromisoformat(f["timestamp_ist"]))
        solar_vals.append(f["predicted_generation_kw"].get("solar_pv", 0))
        wind_vals.append(f["predicted_generation_kw"].get("wind", 0))
        demand_vals.append(f["predicted_demand_kw"])

    renewable = [s + w for s, w in zip(solar_vals, wind_vals)]

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    ax.fill_between(times, renewable, alpha=0.3, color=COLORS["green"], label="Solar + Wind")
    ax.plot(times, renewable, color=COLORS["green"], linewidth=2)
    ax.plot(times, demand_vals, color=COLORS["red"], linewidth=2, label="Demand", linestyle="--")
    ax.set_xlabel("Time (IST)", color="white")
    ax.set_ylabel("Power (kW)", color="white")
    ax.set_title("Predicted Renewable Generation vs Demand", color="white", fontweight="bold")
    ax.legend(facecolor="#16213e", edgecolor="#333", labelcolor="white")
    ax.tick_params(colors="white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.xticks(rotation=45)
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "renewable_vs_demand.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_model_metrics(metrics):
    ensure_charts_dir()
    models = ["solar", "wind", "demand"]
    mae_vals = [metrics[m]["test"]["mae"] for m in models]
    rmse_vals = [metrics[m]["test"]["rmse"] for m in models]
    r2_vals = [metrics[m]["test"]["r2"] for m in models]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Model Evaluation Metrics", fontsize=14, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a2e")

    colors = [COLORS["solar"], COLORS["wind"], COLORS["demand"]]

    for i, (ax, model_name, vals) in enumerate(zip(axes, ["Solar", "Wind", "Demand"], [mae_vals, rmse_vals, r2_vals])):
        ax.set_facecolor("#16213e")
        ax.bar(models, vals, color=colors, alpha=0.8)
        ax.set_title(f"{model_name} Model" if i == 0 else model_name, color="white")
        ax.set_ylabel("Score", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#333")
        for j, v in enumerate(vals):
            ax.text(j, v + max(vals) * 0.02, f"{v:.3f}", ha="center", color="white", fontsize=10)

    axes[0].set_title("MAE (lower is better)", color="white")
    axes[1].set_title("RMSE (lower is better)", color="white")
    axes[2].set_title("R² Score (closer to 1 is better)", color="white")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "model_metrics.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_feature_importance(metrics):
    ensure_charts_dir()
    fig, axes = plt.subplots(1, 3, figsize=(20, 6))
    fig.suptitle("Feature Importance", fontsize=14, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a2e")

    model_names = ["solar", "wind", "demand"]
    titles = ["Solar Model", "Wind Model", "Demand Model"]
    bar_colors = [COLORS["solar"], COLORS["wind"], COLORS["demand"]]

    for ax, name, title, color in zip(axes, model_names, titles, bar_colors):
        fi = metrics[name]["feature_importance"]
        features = sorted(fi.keys(), key=lambda k: fi[k], reverse=True)
        importances = [fi[f] for f in features]

        ax.set_facecolor("#16213e")
        y_pos = range(len(features))
        ax.barh(y_pos, importances, color=color, alpha=0.8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels([f.replace("_", " ").title() for f in features], color="white", fontsize=9)
        ax.set_xlabel("Importance", color="white")
        ax.set_title(title, color="white", fontweight="bold")
        ax.tick_params(colors="white")
        ax.invert_yaxis()
        for spine in ax.spines.values():
            spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "feature_importance.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def plot_risk_timeline(forecast_list):
    ensure_charts_dir()
    times = []
    risk_scores = []
    risk_labels = []

    for f in forecast_list:
        t = datetime.fromisoformat(f["timestamp_ist"])
        alerts = f.get("risk_alerts", [])
        score = 0
        label = ""
        for a in alerts:
            if a["risk_level"] == "CRITICAL":
                score = max(score, 4)
            elif a["risk_level"] == "HIGH":
                score = max(score, 3)
            elif a["risk_level"] == "MEDIUM":
                score = max(score, 2)
            elif a["risk_level"] == "LOW":
                score = max(score, 1)
            label = a.get("affected_resource", "")
        times.append(t)
        risk_scores.append(score)
        risk_labels.append(label)

    fig, ax = plt.subplots(figsize=(14, 4))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    color_map = {0: COLORS["green"], 1: "#8BC34A", 2: COLORS["orange"], 3: COLORS["demand"], 4: COLORS["red"]}
    colors = [color_map.get(s, COLORS["green"]) for s in risk_scores]

    ax.bar(times, risk_scores, color=colors, width=0.04, alpha=0.8)
    ax.set_xlabel("Time (IST)", color="white")
    ax.set_ylabel("Risk Level", color="white")
    ax.set_title("Risk Timeline (24h)", color="white", fontweight="bold")
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_yticklabels(["None", "LOW", "MEDIUM", "HIGH", "CRITICAL"], color="white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.tick_params(colors="white")
    plt.xticks(rotation=45)
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "risk_timeline.png")
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return path


def generate_all_charts(df, metrics, forecast_list, solar_y_actual, solar_y_pred,
                         wind_y_actual, wind_y_pred, demand_y_actual, demand_y_pred):
    charts = {}
    charts["weather_analysis"] = plot_weather_analysis(df)
    charts["solar_prediction"] = plot_solar_prediction(solar_y_actual, solar_y_pred)
    charts["wind_prediction"] = plot_wind_prediction(wind_y_actual, wind_y_pred)
    charts["demand_prediction"] = plot_demand_prediction(demand_y_actual, demand_y_pred)
    charts["weather_impact"] = plot_weather_impact(df)

    if forecast_list:
        charts["resource_capacity"] = plot_resource_capacity(forecast_list[0])
        charts["renewable_vs_demand"] = plot_renewable_vs_demand(forecast_list)
        charts["risk_timeline"] = plot_risk_timeline(forecast_list)

    charts["model_metrics"] = plot_model_metrics(metrics)
    charts["feature_importance"] = plot_feature_importance(metrics)

    print(f"Generated {len(charts)} charts in {CHARTS_DIR}")
    return charts


if __name__ == "__main__":
    print("Visualization module loaded. Run from app.py or train_models.py.")
