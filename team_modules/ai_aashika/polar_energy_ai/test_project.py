import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


def training_df():
    """Merged RESOURCES + WEATHER sections from data/ai_history.json."""
    from history_store import load_history, to_training_dataframe
    df = to_training_dataframe(load_history())
    assert df is not None and not df.empty, "AI history archive is empty - run run_all.py first"
    return df


def test_timestamps_are_ist():
    df = training_df()
    ts = pd.to_datetime(df["timestamp_ist"].iloc[0])
    assert ts.tzinfo is not None, "Timestamps must have timezone info"


def test_solar_never_exceeds_300():
    df = training_df()
    max_solar = df["solar_actual_kw"].max()
    assert max_solar <= 300, f"Solar exceeded 300 kW: {max_solar}"


def test_wind_never_exceeds_300():
    df = training_df()
    max_wind = df["wind_actual_kw"].max()
    assert max_wind <= 300, f"Wind exceeded 300 kW: {max_wind}"


def test_solar_zero_when_sun_down():
    """Solar output must shift automatically with the real date: = 0 whenever the
    sun is actually below the horizon (night hours / polar night)."""
    from solar_utils import solar_elevation_deg
    with open(os.path.join(BASE_DIR, "shared", "station_config.json")) as f:
        cfg = json.load(f)
    lat = cfg["station"]["latitude"]
    df = training_df()
    df["ts"] = pd.to_datetime(df["timestamp_ist"], format="ISO8601", errors="coerce")
    elev = df["ts"].apply(lambda t: solar_elevation_deg(t.to_pydatetime(), lat))
    bad = df[(elev <= 0) & (df["solar_actual_kw"] > 0)]
    assert len(bad) == 0, f"Solar found while sun below horizon (auto-shift failed): {len(bad)} rows"


def test_wind_zero_outside_range():
    df = training_df()
    below_cutin = df[df["wind_speed_mps"] < 3]
    assert (below_cutin["wind_actual_kw"] == 0).all(), "Wind output should be 0 below 3 m/s"
    above_cutoff = df[df["wind_speed_mps"] > 25]
    assert (above_cutoff["wind_actual_kw"] == 0).all(), "Wind output should be 0 above 25 m/s"


def test_demand_positive():
    df = training_df()
    assert (df["demand_actual_kw"] > 0).all(), "Demand must be positive"


def test_cold_increases_demand():
    """Same hour, only colder -> trained demand model must predict higher demand."""
    import pickle
    from predict_24h import prepare_features
    model_path = os.path.join(BASE_DIR, "models", "demand_model.pkl")
    with open(model_path, "rb") as f:
        demand_model = pickle.load(f)

    base = {"timestamp_ist": "2026-09-09T12:00:00+05:30", "wind_speed_mps": 8,
            "snowfall_mm": 0, "cloud_cover_pct": 50, "wind_direction_deg": 200,
            "pressure_hpa": 1013, "solar_irradiance_wm2": 300}
    cold = dict(base, temperature_c=-30, feels_like_c=-38)
    warm = dict(base, temperature_c=-10, feels_like_c=-14)

    _, _, f_cold = prepare_features(cold, prev_demand=190, rolling_demand=190)
    _, _, f_warm = prepare_features(warm, prev_demand=190, rolling_demand=190)
    p_cold = float(demand_model.predict(f_cold)[0])
    p_warm = float(demand_model.predict(f_warm)[0])
    assert p_cold > p_warm, f"Cold demand ({p_cold}) should be higher than warm ({p_warm})"


def test_cloud_reduces_solar():
    """Cloudy sky -> lower solar irradiance -> the trained solar model must
    predict less solar than an otherwise-identical clear hour."""
    import pickle
    from predict_24h import prepare_features
    import solar_utils
    with open(os.path.join(BASE_DIR, "shared", "station_config.json")) as f:
        cfg = json.load(f)
    lat = cfg["station"]["latitude"]
    model_path = os.path.join(BASE_DIR, "models", "solar_model.pkl")
    with open(model_path, "rb") as f:
        solar_model = pickle.load(f)

    ts = datetime.fromisoformat("2026-09-09T12:00:00+05:30")
    elev = solar_utils.solar_elevation_deg(ts, lat)
    irr_clear = solar_utils.solar_irradiance_base(elev, 10)
    irr_cloudy = solar_utils.solar_irradiance_base(elev, 90)

    clear = {"timestamp_ist": ts.isoformat(), "solar_irradiance_wm2": irr_clear,
             "temperature_c": -20, "snowfall_mm": 0, "cloud_cover_pct": 10}
    cloudy = dict(clear, cloud_cover_pct=90, solar_irradiance_wm2=irr_cloudy)

    f_clear = prepare_features(clear, prev_solar=50)[0]
    f_cloudy = prepare_features(cloudy, prev_solar=50)[0]
    p_clear = float(solar_model.predict(f_clear)[0])
    p_cloudy = float(solar_model.predict(f_cloudy)[0])
    assert p_clear > p_cloudy, f"Clear sky solar ({p_clear}) should be higher than cloudy ({p_cloudy})"


def test_storm_alert_at_correct_time():
    from risk_alerts import generate_all_alerts
    config_path = os.path.join(BASE_DIR, "shared", "station_config.json")
    with open(config_path) as f:
        config = json.load(f)

    weather_15h = {
        "timestamp_ist": "2026-09-09T15:30:00+05:30",
        "temperature_c": -10,
        "wind_speed_mps": 8,
        "cloud_cover_pct": 50,
        "solar_irradiance_wm2": 200,
        "snowfall_mm": 0,
    }
    alerts = generate_all_alerts(weather_15h, 100, 150, 100)
    storm_alerts = [a for a in alerts if "storm" in a.get("explanation", "").lower() or "Storm" in a.get("affected_resource", "")]
    assert len(storm_alerts) > 0, "Storm alert should appear at 15:00-15:59 IST"


def test_json_file_created():
    json_path = os.path.join(BASE_DIR, "output", "ai_forecast.json")
    assert os.path.exists(json_path), "ai_forecast.json not found"
    with open(json_path) as f:
        data = json.load(f)
    assert "forecast" in data, "JSON must contain forecast"
    assert "generated_at_ist" in data, "JSON must contain generated_at_ist"


def test_charts_created():
    charts_dir = os.path.join(BASE_DIR, "output", "charts")
    assert os.path.exists(charts_dir), "Charts directory not found"
    charts = os.listdir(charts_dir)
    png_charts = [c for c in charts if c.endswith(".png")]
    assert len(png_charts) >= 5, f"Expected at least 5 charts, found {len(png_charts)}"


def test_auto_failover_reranks():
    """Failed resource must be dropped from the AI-ranked mix; next best takes over."""
    from predict_24h import recommend_resource_mix

    def entry(**overrides):
        base = {
            "availability": {"wind": "available", "geothermal": "available",
                             "hydropower": "available", "solar_pv": "available"},
            "predicted_generation_kw": {"wind": 120.0, "geothermal": 80.0,
                                        "hydropower": 60.0, "solar_pv": 30.0},
            "predicted_demand_kw": 50.0,
        }
        base.update(overrides)
        return base

    before = recommend_resource_mix(entry())
    assert before["primary"]["name"] == "Wind", f"expected Wind primary, got {before['primary']['name']}"

    failed = dict(entry())
    failed["availability"]["wind"] = "not available"
    failed["predicted_generation_kw"]["wind"] = 0
    after = recommend_resource_mix(failed)

    picks = [after["primary"]["name"], after["secondary"]["name"], after["tertiary"]["name"]]
    assert "Wind" not in picks, "failed resource must not appear in the new mix"
    assert after["primary"]["name"] == "Hydro", f"expected Hydro primary, got {picks}"

    fo_path = os.path.join(BASE_DIR, "output", "failover.json")
    assert os.path.exists(fo_path), "failover.json not found"
    with open(fo_path) as f:
        fo = json.load(f)
    assert "failures" in fo and "switched_hours" in fo, "failover.json missing expected keys"
    for r in fo["switched_hours"]:
        picks2 = [r["after"]["primary"]["name"], r["after"]["secondary"]["name"],
                  r["after"]["tertiary"]["name"]]
        assert r["resource_name"] not in picks2, \
            f"{r['resource_name']} still present after failover at {r['timestamp_ist']}"


def run_test_suite():
    tests = [
        ("Timestamps are in IST", test_timestamps_are_ist),
        ("Solar never exceeds 300 kW", test_solar_never_exceeds_300),
        ("Wind never exceeds 300 kW", test_wind_never_exceeds_300),
        ("Solar only when sun up (auto-shift)", test_solar_zero_when_sun_down),
        ("Wind = 0 below 3 and above 25 m/s", test_wind_zero_outside_range),
        ("Demand prediction is positive", test_demand_positive),
        ("Cold weather increases demand", test_cold_increases_demand),
        ("Cloud cover reduces solar", test_cloud_reduces_solar),
        ("Storm alert at correct time", test_storm_alert_at_correct_time),
        ("JSON forecast created", test_json_file_created),
        ("Charts created", test_charts_created),
        ("Auto-failover re-ranks the mix", test_auto_failover_reranks),
    ]

    results = []
    passed = 0
    failed = 0
    for name, func in tests:
        try:
            func()
            results.append((name, "PASS", ""))
            passed += 1
        except AssertionError as e:
            results.append((name, "FAIL", str(e)))
            failed += 1
        except Exception as e:
            results.append((name, "ERROR", str(e)))
            failed += 1

    return results, passed, failed


def run_all_tests():
    print("=" * 60)
    print("Running Tests")
    print("=" * 60)

    results, passed, failed = run_test_suite()

    for name, status, msg in results:
        print(f"PASS: {name}" if status == "PASS" else f"FAIL: {name}: {msg}")

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(results)}")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
