def schedule_deferrable(forecast, deferrable_kw=20, run_hours_per_day=10):
    for row in forecast:
        row["demand_original_kw"] = row["demand_kw"]
        row["deferrable_scheduled"] = False

        row["demand_kw"] = round(row["demand_kw"] - deferrable_kw, 2)
        renewable = row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row.get("extra_renewable_kw", 0)
        row["surplus_kw"] = round(max(0, renewable - row["demand_kw"]), 2)
        row["deficit_kw"] = round(max(0, row["demand_kw"] - renewable), 2)

    ranked = sorted(forecast, key=lambda r: r["surplus_kw"], reverse=True)
    chosen_timestamps = {r["timestamp"] for r in ranked[:run_hours_per_day]}

    for row in forecast:
        if row["timestamp"] in chosen_timestamps:
            row["demand_kw"] = round(row["demand_kw"] + deferrable_kw, 2)
            row["deferrable_scheduled"] = True

    for row in forecast:
        renewable = row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row.get("extra_renewable_kw", 0)
        row["surplus_kw"] = round(max(0, renewable - row["demand_kw"]), 2)
        row["deficit_kw"] = round(max(0, row["demand_kw"] - renewable), 2)

    scheduled = [row["timestamp"] for row in forecast if row["deferrable_scheduled"]]
    return scheduled


def print_load_schedule(forecast, deferrable_name="WaterHeating", deferrable_kw=20):
    print("\n--- LOAD SCHEDULING (Deferrable: " + deferrable_name + f" {deferrable_kw} kW) ---")
    print(f"{'Timestamp':>20} | {'Demand':>7} | {'Renew':>7} | {'Schedule':>8}")
    print("-" * 48)
    for row in forecast:
        mark = "RUN" if row.get("deferrable_scheduled") else "off"
        renew = row["solar_kw"] + row["wind_kw"] + row["hydro_kw"]
        print(f"{row['timestamp']:>20} | {row['demand_kw']:>7.1f} | {renew:>7.1f} | {mark:>8}")