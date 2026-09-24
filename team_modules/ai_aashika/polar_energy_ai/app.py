import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, jsonify, send_from_directory

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def get_forecast_data():
    path = os.path.join(BASE_DIR, "output", "ai_forecast.json")
    return load_json(path)


def get_metrics_data():
    path = os.path.join(BASE_DIR, "output", "model_metrics.json")
    return load_json(path)


def get_config_data():
    path = os.path.join(BASE_DIR, "shared", "station_config.json")
    return load_json(path)


def get_weather_cache():
    path = os.path.join(BASE_DIR, "data", "latest_weather_data.json")
    return load_json(path)


def get_failover_data():
    path = os.path.join(BASE_DIR, "output", "failover.json")
    return load_json(path)


@app.route("/")
def home():
    forecast = get_forecast_data()
    metrics = get_metrics_data()
    config = get_config_data()
    weather = get_weather_cache()

    current_weather = {}
    source = "unknown"
    if weather:
        current_weather = weather.get("current", {})
        source = weather.get("source", "unknown")

    top_alert = None
    if forecast and forecast.get("forecast"):
        first_entry = forecast["forecast"][0]
        alerts = first_entry.get("risk_alerts", [])
        if alerts:
            top_alert = alerts[0]

    confidence = {}
    if metrics:
        confidence = {
            "solar": round(metrics.get("solar", {}).get("test", {}).get("r2", 0) * 100, 1),
            "wind": round(metrics.get("wind", {}).get("test", {}).get("r2", 0) * 100, 1),
            "demand": round(metrics.get("demand", {}).get("test", {}).get("r2", 0) * 100, 1),
        }

    predicted = {}
    if forecast and forecast.get("forecast"):
        first = forecast["forecast"][0]
        predicted = first.get("predicted_generation_kw", {})
        predicted["demand"] = first.get("predicted_demand_kw", 0)

    return render_template("home.html",
                           current_weather=current_weather,
                           weather_source=source,
                           predicted=predicted,
                           top_alert=top_alert,
                           confidence=confidence,
                           forecast_generated=forecast.get("generated_at_ist", "") if forecast else "",
                           config=config)


@app.route("/weather")
def weather():
    weather_data = get_weather_cache()
    forecast = get_forecast_data()
    return render_template("weather.html",
                           weather_data=weather_data,
                           forecast=forecast)


@app.route("/predictions")
def predictions():
    forecast = get_forecast_data()
    metrics = get_metrics_data()
    config = get_config_data()
    charts = ["solar_prediction", "wind_prediction", "demand_prediction",
              "model_metrics", "feature_importance"]
    return render_template("predictions.html",
                           forecast=forecast,
                           metrics=metrics,
                           charts=charts)


@app.route("/resources")
def resources():
    forecast = get_forecast_data()
    config = get_config_data()
    failover = get_failover_data()
    return render_template("resources.html",
                           forecast=forecast,
                           config=config,
                           failover=failover)


@app.route("/alerts")
def alerts():
    forecast = get_forecast_data()
    return render_template("alerts.html",
                           forecast=forecast)


@app.route("/reports")
def reports():
    charts_dir = os.path.join(BASE_DIR, "output", "charts")
    chart_files = []
    if os.path.exists(charts_dir):
        chart_files = [f for f in os.listdir(charts_dir) if f.endswith(".png")]
    return render_template("reports.html",
                           chart_files=chart_files,
                           has_data=os.path.exists(os.path.join(BASE_DIR, "data", "ai_history.json")),
                           has_forecast=os.path.exists(os.path.join(BASE_DIR, "output", "ai_forecast.json")))


@app.route("/api/forecast")
def api_forecast():
    data = get_forecast_data()
    if data:
        return jsonify(data)
    return jsonify({"error": "No forecast data. Run predict_24h.py first."}), 404


@app.route("/api/weather")
def api_weather():
    data = get_weather_cache()
    if data:
        return jsonify(data)
    return jsonify({"error": "No weather data."}), 404


@app.route("/api/metrics")
def api_metrics():
    data = get_metrics_data()
    if data:
        return jsonify(data)
    return jsonify({"error": "No metrics data."}), 404


@app.route("/charts/<filename>")
def chart_image(filename):
    charts_dir = os.path.join(BASE_DIR, "output", "charts")
    return send_from_directory(charts_dir, filename)


@app.route("/data/<filename>")
def data_file(filename):
    data_dir = os.path.join(BASE_DIR, "data")
    return send_from_directory(data_dir, filename)


@app.route("/output/<filename>")
def output_file(filename):
    output_dir = os.path.join(BASE_DIR, "output")
    return send_from_directory(output_dir, filename)


if __name__ == "__main__":
    print("=" * 60)
    print("  AI-Driven Smart Energy Management System")
    print("  Polar Research Station - AI/ML Dashboard")
    print("  Running on http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
