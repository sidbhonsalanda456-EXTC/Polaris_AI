import pulp

FUEL_COST_PER_LITER = 10.0
BATTERY_DEGRADATION_COST = 0.1
UNMET_PENALTY = 10000.0

SOLAR_PRIORITY = 0.0
WIND_PRIORITY = 0.0005
HYDRO_PRIORITY = 0.001
GEOTHERMAL_PRIORITY = 0.0011
MARINE_PRIORITY = 0.0012
BIOMASS_PRIORITY = 0.0013
SOLAR_THERMAL_PRIORITY = 0.0014
H2_PRIORITY = 0.0015
CHARGE_BONUS = 0.0002

H2_COST_PER_KWH = 2.6
CHP_COST_PER_KWH = 3.0

PRE_CHARGE_LOOKAHEAD_HOURS = 4.0
PRE_CHARGE_TARGET_SOC_PCT = 95.0
PRE_CHARGE_REWARD_PER_KWH = 1.0


def _row_is_failure(row):
    for status in ("solar_status", "wind_status", "hydro_status",
                   "generator_status"):
        if row.get(status) == "UNAVAILABLE":
            return True
    if row.get("disaster") not in ("NONE", "", None):
        return True
    return (row.get("deficit_kw") or 0) > 0.01


def build_precharge_flags(forecast, lookahead_hours=PRE_CHARGE_LOOKAHEAD_HOURS):
    """True for rows that come *before* a predicted failure/storm within the
    look-ahead window, so the AI banks energy into the battery in advance."""
    n = len(forecast)
    flags = [False] * n
    next_fail = None
    for i in range(n):
        if next_fail is None or i >= next_fail:
            next_fail = None
            for j in range(i, n):
                if _row_is_failure(forecast[j]):
                    next_fail = j
                    break
        if next_fail is not None and next_fail > i:
            steps = next_fail - i
            dt = forecast[i].get("step_hours", 1.0)
            if steps * dt <= lookahead_hours:
                flags[i] = True
    return flags


def _renew(kw_avail, remaining_kwh, dt_hours):
    used = min(max(0.0, kw_avail) * dt_hours, remaining_kwh)
    return used, remaining_kwh - used


def fallback_solution(solar_avail_kw, wind_avail_kw, demand_kw, battery,
                      generator, critical_kw, gen_ok, extra_renew_avail_kw=0,
                      hydro_avail_kw=0, dt_hours=1.0, geothermal_avail_kw=0,
                      marine_avail_kw=0, biomass_avail_kw=0,
                      solar_thermal_avail_kw=0, h2_fc_avail_kw=0,
                      chp_avail_kw=0):
    remaining_kwh = demand_kw * dt_hours

    solar_kwh, remaining_kwh = _renew(solar_avail_kw, remaining_kwh, dt_hours)
    wind_kwh, remaining_kwh = _renew(wind_avail_kw, remaining_kwh, dt_hours)
    hydro_kwh, remaining_kwh = _renew(hydro_avail_kw, remaining_kwh, dt_hours)
    gth_kwh, remaining_kwh = _renew(geothermal_avail_kw, remaining_kwh, dt_hours)
    mar_kwh, remaining_kwh = _renew(marine_avail_kw, remaining_kwh, dt_hours)
    bio_kwh, remaining_kwh = _renew(biomass_avail_kw, remaining_kwh, dt_hours)
    sth_kwh, remaining_kwh = _renew(solar_thermal_avail_kw, remaining_kwh, dt_hours)
    extra_kwh, remaining_kwh = _renew(extra_renew_avail_kw, remaining_kwh, dt_hours)

    batt_disc_kwh = 0.0
    if remaining_kwh > 0 and battery.status != "EMPTY":
        batt_disc_kwh = min(remaining_kwh, battery.available_discharge_kwh,
                            battery.max_discharge_kw * dt_hours)
        remaining_kwh -= batt_disc_kwh

    gen_kwh = 0.0
    if remaining_kwh > 0 and gen_ok:
        gen_kwh = min(remaining_kwh, generator.max_kw * dt_hours)
        remaining_kwh -= gen_kwh

    h2_kwh = 0.0
    if remaining_kwh > 0:
        h2_kwh = min(remaining_kwh, max(0.0, h2_fc_avail_kw) * dt_hours)
        remaining_kwh -= h2_kwh

    chp_kwh = 0.0
    if remaining_kwh > 0:
        chp_kwh = min(remaining_kwh, max(0.0, chp_avail_kw) * dt_hours)
        remaining_kwh -= chp_kwh

    unmet_kwh = max(0.0, remaining_kwh)

    used_renew_kwh = (solar_kwh + wind_kwh + hydro_kwh + gth_kwh + mar_kwh
                      + bio_kwh + sth_kwh + extra_kwh)
    avail_renew_kwh = sum(max(0.0, a) for a in (
        solar_avail_kw, wind_avail_kw, hydro_avail_kw, geothermal_avail_kw,
        marine_avail_kw, biomass_avail_kw, solar_thermal_avail_kw,
        extra_renew_avail_kw)) * dt_hours
    surplus_kwh = max(0.0, avail_renew_kwh - used_renew_kwh)
    headroom_kwh = max(0.0, battery.max_energy_kwh - battery.stored_energy_kwh)
    charge_kwh = min(surplus_kwh, battery.max_charge_kw * dt_hours, headroom_kwh)
    charge_kwh = 0.0 if unmet_kwh > 0.01 else charge_kwh

    return {
        "solar_used_kw": solar_kwh / dt_hours,
        "wind_used_kw": wind_kwh / dt_hours,
        "hydro_used_kw": hydro_kwh / dt_hours,
        "geothermal_used_kw": gth_kwh / dt_hours,
        "marine_used_kw": mar_kwh / dt_hours,
        "biomass_used_kw": bio_kwh / dt_hours,
        "solar_thermal_used_kw": sth_kwh / dt_hours,
        "extra_renew_used_kw": extra_kwh / dt_hours,
        "hydrogen_used_kw": h2_kwh / dt_hours,
        "chp_used_kw": chp_kwh / dt_hours,
        "battery_discharge_kw": batt_disc_kwh / dt_hours,
        "battery_charge_kw": charge_kwh / dt_hours,
        "generator_output_kw": gen_kwh / dt_hours,
        "unmet_kw": unmet_kwh / dt_hours,
        "battery_discharge_kwh": batt_disc_kwh,
        "battery_charge_kwh": charge_kwh,
        "feasible": False,
    }


def lp_optimize_step(solar_avail_kw, wind_avail_kw, demand_kw, battery, loads,
                     generator, base_demand_kw=0, generator_status="AVAILABLE",
                     extra_renew_avail_kw=0, hydro_avail_kw=0, dt_hours=1.0,
                     geothermal_avail_kw=0, marine_avail_kw=0,
                     biomass_avail_kw=0, solar_thermal_avail_kw=0,
                     h2_fc_avail_kw=0, chp_avail_kw=0, precharge=False):
    critical_kw = loads.critical_total_kw
    stored = battery.stored_energy_kwh
    min_energy = battery.min_energy_kwh
    max_energy = battery.max_energy_kwh
    gen_ok = generator_status in ("AVAILABLE", "RUNNING")

    demand_kwh = demand_kw * dt_hours
    solar_avail_kwh = max(0.0, solar_avail_kw) * dt_hours
    wind_avail_kwh = max(0.0, wind_avail_kw) * dt_hours
    hydro_avail_kwh = max(0.0, hydro_avail_kw) * dt_hours
    gth_avail_kwh = max(0.0, geothermal_avail_kw) * dt_hours
    mar_avail_kwh = max(0.0, marine_avail_kw) * dt_hours
    bio_avail_kwh = max(0.0, biomass_avail_kw) * dt_hours
    sth_avail_kwh = max(0.0, solar_thermal_avail_kw) * dt_hours
    h2_avail_kwh = max(0.0, h2_fc_avail_kw) * dt_hours
    chp_avail_kwh = max(0.0, chp_avail_kw) * dt_hours
    extra_avail_kwh = max(0.0, extra_renew_avail_kw) * dt_hours
    batt_disc_max_kwh = battery.max_discharge_kw * dt_hours
    batt_chg_max_kwh = battery.max_charge_kw * dt_hours
    gen_min_kwh = generator.min_kw * dt_hours
    gen_max_kwh = generator.max_kw * dt_hours

    prob = pulp.LpProblem("PolarEnergyLP", pulp.LpMinimize)

    solar_used = pulp.LpVariable("solar_used", 0, solar_avail_kwh)
    wind_used = pulp.LpVariable("wind_used", 0, wind_avail_kwh)
    hydro_used = pulp.LpVariable("hydro_used", 0, hydro_avail_kwh)
    gth_used = pulp.LpVariable("geothermal_used", 0, gth_avail_kwh)
    mar_used = pulp.LpVariable("marine_used", 0, mar_avail_kwh)
    bio_used = pulp.LpVariable("biomass_used", 0, bio_avail_kwh)
    sth_used = pulp.LpVariable("solar_thermal_used", 0, sth_avail_kwh)
    extra_renew_used = pulp.LpVariable("extra_renew_used", 0, extra_avail_kwh)
    h2_used = pulp.LpVariable("hydrogen_used", 0, h2_avail_kwh)
    chp_used = pulp.LpVariable("chp_used", 0, chp_avail_kwh)
    batt_disc = pulp.LpVariable("batt_discharge", 0, batt_disc_max_kwh)
    batt_chg = pulp.LpVariable("batt_charge", 0, batt_chg_max_kwh)
    batt_mode = pulp.LpVariable("batt_mode", cat="Binary")
    gen_used = pulp.LpVariable("gen_output", 0, gen_max_kwh if gen_ok else 0)
    gen_on = pulp.LpVariable("gen_on", cat="Binary")
    unmet = pulp.LpVariable("unmet", 0)

    cost_obj = (
        FUEL_COST_PER_LITER * generator.fuel_rate * gen_used
        + H2_COST_PER_KWH * h2_used
        + CHP_COST_PER_KWH * chp_used
        + BATTERY_DEGRADATION_COST * batt_disc
        + UNMET_PENALTY * unmet
        + SOLAR_PRIORITY * solar_used
        + WIND_PRIORITY * wind_used
        + HYDRO_PRIORITY * hydro_used
        + GEOTHERMAL_PRIORITY * gth_used
        + MARINE_PRIORITY * mar_used
        + BIOMASS_PRIORITY * bio_used
        + SOLAR_THERMAL_PRIORITY * sth_used
        + H2_PRIORITY * h2_used
        - CHARGE_BONUS * batt_chg
    )
    if precharge:
        cost_obj += -PRE_CHARGE_REWARD_PER_KWH * batt_chg
    prob += cost_obj

    prob += (solar_used + wind_used + hydro_used + gth_used + mar_used
             + bio_used + sth_used + extra_renew_used + h2_used
             + batt_disc + gen_used + unmet == demand_kwh + batt_chg)

    prob += (solar_used + wind_used + hydro_used + gth_used + mar_used
             + bio_used + sth_used + extra_renew_used + h2_used
             + batt_disc + gen_used >= critical_kw * dt_hours)

    surplus_kwh = max(0.0,
                      solar_avail_kwh + wind_avail_kwh + hydro_avail_kwh
                      + gth_avail_kwh + mar_avail_kwh + bio_avail_kwh
                      + sth_avail_kwh + extra_avail_kwh - demand_kwh)
    prob += batt_chg <= surplus_kwh

    prob += min_energy <= stored - batt_disc + batt_chg
    prob += stored - batt_disc + batt_chg <= max_energy

    prob += batt_chg <= batt_chg_max_kwh * batt_mode
    prob += batt_disc <= batt_disc_max_kwh * (1 - batt_mode)

    if precharge and gen_ok and battery.soc_percent < PRE_CHARGE_TARGET_SOC_PCT:
        prob += batt_disc == 0

    if gen_ok:
        prob += gen_used >= gen_min_kwh * gen_on
        prob += gen_used <= gen_max_kwh * gen_on
    else:
        prob += gen_used == 0

    try:
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
    except Exception:
        return fallback_solution(solar_avail_kw, wind_avail_kw, demand_kw,
                                 battery, generator, critical_kw, gen_ok,
                                 extra_renew_avail_kw, hydro_avail_kw, dt_hours,
                                 geothermal_avail_kw, marine_avail_kw,
                                 biomass_avail_kw, solar_thermal_avail_kw,
                                 h2_fc_avail_kw, chp_avail_kw)

    if pulp.LpStatus[prob.status] != "Optimal":
        return fallback_solution(solar_avail_kw, wind_avail_kw, demand_kw,
                                 battery, generator, critical_kw, gen_ok,
                                 extra_renew_avail_kw, hydro_avail_kw, dt_hours,
                                 geothermal_avail_kw, marine_avail_kw,
                                 biomass_avail_kw, solar_thermal_avail_kw,
                                 h2_fc_avail_kw, chp_avail_kw)

    batt_disc_kwh = max(0.0, pulp.value(batt_disc))
    batt_chg_kwh = max(0.0, pulp.value(batt_chg))
    sols = {
        "solar_used_kw": max(0.0, pulp.value(solar_used)) / dt_hours,
        "wind_used_kw": max(0.0, pulp.value(wind_used)) / dt_hours,
        "hydro_used_kw": max(0.0, pulp.value(hydro_used)) / dt_hours,
        "geothermal_used_kw": max(0.0, pulp.value(gth_used)) / dt_hours,
        "marine_used_kw": max(0.0, pulp.value(mar_used)) / dt_hours,
        "biomass_used_kw": max(0.0, pulp.value(bio_used)) / dt_hours,
        "solar_thermal_used_kw": max(0.0, pulp.value(sth_used)) / dt_hours,
        "extra_renew_used_kw": max(0.0, pulp.value(extra_renew_used)) / dt_hours,
        "hydrogen_used_kw": max(0.0, pulp.value(h2_used)) / dt_hours,
        "chp_used_kw": max(0.0, pulp.value(chp_used)) / dt_hours,
        "battery_discharge_kw": batt_disc_kwh / dt_hours,
        "battery_charge_kw": batt_chg_kwh / dt_hours,
        "generator_output_kw": max(0.0, pulp.value(gen_used)) / dt_hours,
        "unmet_kw": max(0.0, pulp.value(unmet)) / dt_hours,
        "battery_discharge_kwh": batt_disc_kwh,
        "battery_charge_kwh": batt_chg_kwh,
        "feasible": True,
    }
    return sols


def apply_lp_result(battery, generator, sols):
    batt_disc = sols["battery_discharge_kwh"]
    batt_chg = sols["battery_charge_kwh"]
    gen_out = sols["generator_output_kw"]

    stored_new = battery.stored_energy_kwh - batt_disc + batt_chg
    battery.soc_percent = round(stored_new / battery.effective_capacity_kwh * 100, 4)

    if gen_out > 0:
        generator.record_production(gen_out * 1.0)


def run_24h_lp(forecast, battery, loads, generator):
    results = []
    pre_flags = build_precharge_flags(forecast)
    for i, row in enumerate(forecast):
        dt = row.get("step_hours", 1.0)
        pre = pre_flags[i]
        sols = lp_optimize_step(
            solar_avail_kw=row["solar_kw"],
            wind_avail_kw=row["wind_kw"],
            demand_kw=row["demand_kw"],
            battery=battery,
            loads=loads,
            generator=generator,
            generator_status=row.get("generator_status", "AVAILABLE"),
            extra_renew_avail_kw=row.get("extra_renewable_kw", 0),
            hydro_avail_kw=row.get("hydro_kw", 0),
            geothermal_avail_kw=row.get("geothermal_kw", 0),
            marine_avail_kw=row.get("marine_kw", 0),
            biomass_avail_kw=row.get("biomass_kw", 0),
            solar_thermal_avail_kw=row.get("solar_thermal_kw", 0),
            h2_fc_avail_kw=row.get("hydrogen_fc_kw", 0),
            chp_avail_kw=row.get("chp_kw", 0),
            dt_hours=dt,
            precharge=pre,
        )

        other_renew_kw = (sols["geothermal_used_kw"] + sols["marine_used_kw"]
                          + sols["biomass_used_kw"] + sols["solar_thermal_used_kw"])

        supply_total = (
            sols["solar_used_kw"] + sols["wind_used_kw"]
            + sols["hydro_used_kw"] + sols["geothermal_used_kw"]
            + sols["marine_used_kw"] + sols["biomass_used_kw"]
            + sols["solar_thermal_used_kw"] + sols["extra_renew_used_kw"]
            + sols["hydrogen_used_kw"] + sols["chp_used_kw"]
            + sols["battery_discharge_kw"] + sols["generator_output_kw"]
        )

        if sols["battery_discharge_kw"] > 0.01:
            battery_state = "DISCHARGING"
        elif sols["battery_charge_kw"] > 0.01:
            battery_state = "CHARGING"
        else:
            battery_state = "IDLE"

        critical_kw = loads.critical_total_kw
        served_kw = min(row["demand_kw"], supply_total)
        critical_target_kw = min(critical_kw, row["demand_kw"])

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

        apply_lp_result(battery, generator, sols)
        soc_after = battery.soc_percent

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
            "battery_soc_after_pct": soc_after,
            "precharge_flag": pre,
            "precharge_kw": sols["battery_charge_kw"] if pre else 0.0,
            "disaster": row.get("disaster", "NONE"),
            "event": "; ".join(events),
        })
    return results


def print_lp_results(results, show_limit=None):
    header = (f"{'Time (IST)':>16} | {'Solar(kW)':>9} | {'Wind(kW)':>8} | {'Hydro(kW)':>9} | "
              f"{'Other(kW)':>9} | {'BattD(kW)':>9} | {'BattC(kW)':>9} | {'Batt':>11} | "
              f"{'Gen(kW)':>7} | {'H2(kW)':>6} | {'Served(kW)':>10} | {'Met':>3} | "
              f"{'SOC%':>6} | Events")
    print(header)
    print("-" * len(header))
    shown = 0
    for r in results:
        if show_limit and shown >= show_limit:
            print(f"  ... ({len(results) - shown} more rows)")
            break
        met = "Y" if r["critical_load_met"] else "N"
        other = (r["geothermal_used_kw"] + r["marine_used_kw"]
                 + r["biomass_used_kw"] + r["solar_thermal_used_kw"])
        print(f"{r['ts_readable']:>16} | {r['solar_used_kw']:>9.1f} | "
              f"{r['wind_used_kw']:>8.1f} | "
              f"{r['hydro_used_kw']:>9.1f} | {other:>9.1f} | "
              f"{r['battery_discharge_kw']:>9.1f} | "
              f"{r['battery_charge_kw']:>9.1f} | {r['battery_state']:>11} | "
              f"{r['generator_output_kw']:>7.1f} | {r['hydrogen_used_kw']:>6.1f} | "
              f"{r['load_served_kw']:>10.1f} | {met:>3} | "
              f"{r['battery_soc_after_pct']:>6.1f} | {r['event']}")
        shown += 1


def summarize_lp(results, generator):
    sol = sum(r["solar_used_kw"] * r["step_hours"] for r in results)
    win = sum(r["wind_used_kw"] * r["step_hours"] for r in results)
    hyd = sum(r["hydro_used_kw"] * r["step_hours"] for r in results)
    gth = sum(r["geothermal_used_kw"] * r["step_hours"] for r in results)
    mar = sum(r["marine_used_kw"] * r["step_hours"] for r in results)
    bio = sum(r["biomass_used_kw"] * r["step_hours"] for r in results)
    sth = sum(r["solar_thermal_used_kw"] * r["step_hours"] for r in results)
    h2 = sum(r["hydrogen_used_kw"] * r["step_hours"] for r in results)
    chp = sum(r["chp_used_kw"] * r["step_hours"] for r in results)
    renew = sum(r["renewable_used_kw"] * r["step_hours"] for r in results)
    battd = sum(r["battery_discharge_kw"] * r["step_hours"] for r in results)
    battc = sum(r["battery_charge_kw"] * r["step_hours"] for r in results)
    pree = sum(r.get("precharge_kw", 0) * r["step_hours"] for r in results)
    gen = sum(r["generator_output_kw"] * r["step_hours"] for r in results)
    served = sum(r["load_served_kw"] * r["step_hours"] for r in results)
    unmet = sum(r["unmet_kw"] * r["step_hours"] for r in results)
    demand_total = sum(r["demand_kw"] * r["step_hours"] for r in results)
    surplus_total = sum(r["surplus_renewable_kw"] * r["step_hours"] for r in results)

    crit = sum(1 for r in results if r["critical_load_met"])
    nonc = sum(1 for r in results if r["noncritical_load_met"])
    FAILURE_MARKERS = ("SOLAR FAILURE", "WIND FAILURE", "HYDRO FAILURE",
                       "GENERATOR DOWN")
    shifted = sum(1 for r in results
                  if any(m in r["event"] for m in FAILURE_MARKERS))
    dis = sum(1 for r in results
              if r.get("disaster") not in ("NONE", "", None))
    total = len(results)

    print("\n" + "=" * 58)
    print("ENERGY OPTIMIZATION SUMMARY (24 HOURS)")
    print("=" * 58)
    print(f"  Total demand:               {demand_total:9.1f} kWh")
    print(f"  Total renewable used:       {renew:9.1f} kWh")
    print(f"    - Solar:                  {sol:9.1f} kWh")
    print(f"    - Wind:                   {win:9.1f} kWh")
    print(f"    - Hydro:                  {hyd:9.1f} kWh")
    print(f"    - Geothermal:             {gth:9.1f} kWh")
    print(f"    - Marine:                 {mar:9.1f} kWh")
    print(f"    - Biomass/Biogas:         {bio:9.1f} kWh")
    print(f"    - Solar Thermal:          {sth:9.1f} kWh")
    print(f"    - Hydrogen fuel cell:     {h2:9.1f} kWh")
    print(f"  Total battery discharge:    {battd:9.1f} kWh")
    print(f"  Total battery charge:       {battc:9.1f} kWh")
    print(f"  AI PRE-CHARGE banked:       {pree:9.1f} kWh  (before predicted storm)")
    print(f"  Total diesel generator:     {gen:9.1f} kWh")
    print(f"  Total CHP/cogeneration:     {chp:9.1f} kWh")
    print(f"  Total energy served:        {served:9.1f} kWh")
    print(f"  Total unmet load:           {unmet:9.1f} kWh")
    print(f"  Surplus renewable energy:   {surplus_total:9.1f} kWh  (PLUS POINT)")
    renew_share = (renew / demand_total * 100) if demand_total else 0
    print(f"  Renewable share of demand:  {renew_share:8.1f} %")
    print(f"  Diesel fuel used:           {generator.total_fuel_used_liters:9.1f} L")
    print(f"  Critical load met:          {crit}/{total}")
    print(f"  Non-critical load met:      {nonc}/{total}")
    print(f"  Auto shift events:          {shifted}")
    print(f"  Disaster-affected steps:    {dis}  (flood/storm/tsunami)")
    print("=" * 58)


def print_optimal_decision(results, battery, sensor_row=None):
    last = results[-1]
    avg = lambda key: sum(r[key] for r in results) / len(results)

    if sensor_row is not None:
        print("\n" + "=" * 46)
        print(f"FINAL OPTIMAL DECISION @ {sensor_row.get('ts_readable', sensor_row['timestamp'])}")
        print("=" * 46)
        print(f"  Solar used:           {sensor_row['solar_used_kw']:7.2f} kW")
        print(f"  Wind used:            {sensor_row['wind_used_kw']:7.2f} kW")
        print(f"  Hydro used:           {sensor_row['hydro_used_kw']:7.2f} kW")
        print(f"  Battery discharge:    {sensor_row['battery_discharge_kw']:7.2f} kW")
        print(f"  Battery charge:       {sensor_row['battery_charge_kw']:7.2f} kW")
        print(f"  Battery state:        {sensor_row['battery_state']}")
        print(f"  Generator:            {sensor_row['generator_output_kw']:7.2f} kW")
        print(f"  Battery SOC after:    {sensor_row['battery_soc_after_pct']:6.2f} %")
        print(f"  Critical loads:       {'MET' if sensor_row['critical_load_met'] else 'UNMET'}")
        return

    print("\n" + "=" * 46)
    print("FINAL OPTIMAL DECISION (avg kW per step, 24h)")
    print("=" * 46)
    print(f"  Solar used:           {avg('solar_used_kw'):7.2f} kW")
    print(f"  Wind used:            {avg('wind_used_kw'):7.2f} kW")
    print(f"  Hydro used:           {avg('hydro_used_kw'):7.2f} kW")
    print(f"  Battery discharge:    {avg('battery_discharge_kw'):7.2f} kW")
    print(f"  Battery charge:       {avg('battery_charge_kw'):7.2f} kW")
    print(f"  Battery state:        {last['battery_state']}")
    print(f"  Generator:            {avg('generator_output_kw'):7.2f} kW")
    print(f"  Battery SOC after:    {battery.soc_percent:6.2f} %")
    print(f"  Critical loads:       {'MET' if last['critical_load_met'] else 'UNMET'}")


def print_legend():
    print("\n" + "=" * 46)
    print("LEGEND")
    print("=" * 46)
    print("  Solar(kW)/Wind(kW)/Hydro(kW) : power used from each source")
    print("  BattD/BattC (kW)             : battery discharge/charge power")
    print("  Batt                         : battery state CHARGING/DISCHARGING/IDLE")
    print("  Gen(kW)                      : generator output")
    print("  Met = Y                      : critical loads FULLY satisfied this step")
    print("  X/total (e.g. 24/24)         : steps where critical load was met / total steps")
    print("  Auto shift events            : steps where a source failed and the AI")
    print("                                 automatically switched to the best source")
    print("  PRE-CHARGE                   : AI spotted a predicted failure/storm in the")
    print("                                 upcoming hours and banked battery energy early")
    print("  RESERVE HOLD                 : AI holds battery (no discharge) to keep it")
    print("                                 charged for the predicted failure window")


if __name__ == "__main__":
    import sys
    from battery import Battery
    from loads import StationLoads
    from generator import Generator
    from forecast_24h import generate_24h_forecast

    scenario = sys.argv[1] if len(sys.argv) > 1 else "auto"

    battery = Battery(capacity_kwh=2000, soc_percent=70, soh_percent=80)
    loads = StationLoads()
    generator = Generator(min_kw=20, max_kw=100)

    forecast = generate_24h_forecast(interval="hourly", scenario=scenario)
    results = run_24h_lp(forecast, battery, loads, generator)
    print_lp_results(results)
    summarize_lp(results, generator)
    print_optimal_decision(results, battery, sensor_row=results[-1])
    print_legend()
    print(f"\nFINAL STATE: {battery} | {generator}")