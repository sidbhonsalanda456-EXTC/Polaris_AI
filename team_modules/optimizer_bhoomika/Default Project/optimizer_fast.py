from optimizer_lp import fallback_solution, build_precharge_flags


def run_fast(forecast, battery, loads, generator):
    results = []
    pre_flags = build_precharge_flags(forecast)
    for i, row in enumerate(forecast):
        dt = row.get("step_hours", 1.0)
        gen_ok = row.get("generator_status", "AVAILABLE") in ("AVAILABLE", "RUNNING")
        pre = pre_flags[i]

        sols = fallback_solution(
            solar_avail_kw=row["solar_kw"],
            wind_avail_kw=row["wind_kw"],
            demand_kw=row["demand_kw"],
            battery=battery,
            generator=generator,
            critical_kw=loads.critical_total_kw,
            gen_ok=gen_ok,
            extra_renew_avail_kw=row.get("extra_renewable_kw", 0),
            hydro_avail_kw=row.get("hydro_kw", 0),
            geothermal_avail_kw=row.get("geothermal_kw", 0),
            marine_avail_kw=row.get("marine_kw", 0),
            biomass_avail_kw=row.get("biomass_kw", 0),
            solar_thermal_avail_kw=row.get("solar_thermal_kw", 0),
            h2_fc_avail_kw=row.get("hydrogen_fc_kw", 0),
            chp_avail_kw=row.get("chp_kw", 0),
            dt_hours=dt,
        )

        other_renew_kw = (sols["geothermal_used_kw"] + sols["marine_used_kw"]
                          + sols["biomass_used_kw"] + sols["solar_thermal_used_kw"])

        supply_total = (
            sols["solar_used_kw"] + sols["wind_used_kw"]
            + sols["hydro_used_kw"] + other_renew_kw
            + sols["extra_renew_used_kw"] + sols["hydrogen_used_kw"]
            + sols["chp_used_kw"]
            + sols["battery_discharge_kw"] + sols["generator_output_kw"]
        )

        if sols["battery_discharge_kw"] > 0.01:
            battery_state = "DISCHARGING"
        elif sols["battery_charge_kw"] > 0.01:
            battery_state = "CHARGING"
        else:
            battery_state = "IDLE"

        critical_kw = loads.critical_total_kw
        critical_target_kw = min(critical_kw, row["demand_kw"])
        served_kw = min(row["demand_kw"], supply_total)

        shift_sources = []
        if row["solar_status"] == "UNAVAILABLE":
            shift_sources.append("SOLAR FAILURE -> shifted to best source")
        if row["wind_status"] == "UNAVAILABLE":
            shift_sources.append("WIND FAILURE -> shifted to best source")
        if row["hydro_status"] == "UNAVAILABLE":
            shift_sources.append("HYDRO FAILURE -> shifted to best source")
        if row["generator_status"] == "UNAVAILABLE":
            shift_sources.append("GENERATOR DOWN -> renewable/battery")
        if row.get("disaster") not in ("NONE", "", None):
            shift_sources.append(f"DISASTER {row['disaster']} -> "
                                 "derates + pre-charge battery")

        events = list(shift_sources)
        if pre:
            if sols["battery_charge_kw"] > 0.01:
                events.append("PRE-CHARGE: failure predicted -> banking energy")
            elif sols["battery_discharge_kw"] <= 0.01:
                events.append("RESERVE HOLD: battery saved for upcoming failure")

        from optimizer_lp import apply_lp_result
        apply_lp_result(battery, generator, sols)

        results.append({
            "timestamp": row["timestamp"],
            "ts_readable": row["ts_readable"],
            "hour": row["hour"],
            "step_hours": dt,
            "solar_status": row["solar_status"],
            "wind_status": row["wind_status"],
            "hydro_status": row["hydro_status"],
            "generator_status": row["generator_status"],
            "demand_kw": row["demand_kw"],
            "renewable_avail_kw": row["renewable_kw"],
            "surplus_renewable_kw": row["surplus_kw"],
            "solar_used_kw": sols["solar_used_kw"],
            "wind_used_kw": sols["wind_used_kw"],
            "hydro_used_kw": sols["hydro_used_kw"],
            "geothermal_used_kw": sols["geothermal_used_kw"],
            "marine_used_kw": sols["marine_used_kw"],
            "biomass_used_kw": sols["biomass_used_kw"],
            "solar_thermal_used_kw": sols["solar_thermal_used_kw"],
            "hydrogen_used_kw": sols["hydrogen_used_kw"],
            "chp_used_kw": sols["chp_used_kw"],
            "renewable_used_kw": (sols["solar_used_kw"] + sols["wind_used_kw"]
                                   + sols["hydro_used_kw"] + other_renew_kw
                                   + sols["extra_renew_used_kw"]
                                   + sols["hydrogen_used_kw"]),
            "battery_discharge_kw": sols["battery_discharge_kw"],
            "battery_charge_kw": sols["battery_charge_kw"],
            "battery_discharge_kwh": sols["battery_discharge_kwh"],
            "battery_charge_kwh": sols["battery_charge_kwh"],
            "battery_state": battery_state,
            "generator_output_kw": sols["generator_output_kw"],
            "load_served_kw": served_kw,
            "unmet_kw": sols["unmet_kw"],
            "critical_load_met": served_kw >= critical_target_kw,
            "noncritical_load_met": served_kw >= row["demand_kw"],
            "battery_soc_after_pct": battery.soc_percent,
            "precharge_flag": pre,
            "precharge_kw": sols["battery_charge_kw"] if pre else 0.0,
            "disaster": row.get("disaster", "NONE"),
            "event": "; ".join(events),
        })
    return results