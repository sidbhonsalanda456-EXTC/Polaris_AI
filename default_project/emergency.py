class EmergencySystem:
    def __init__(self, battery_low_soc=25.0, generator_capacity=100.0):
        self.battery_low_soc = battery_low_soc
        self.generator_capacity = generator_capacity
        self.alerts = []
        self.disaster_warnings = []
        self.total_unmet_kwh = 0.0

    def monitor(self, results, loads):
        critical_kw = loads.critical_total_kw
        for r in results:
            ts = r.get("ts_readable", r["timestamp"])
            unmet = r["unmet_kw"]
            self.total_unmet_kwh += unmet * r.get("step_hours", 1.0)

            if unmet > 0.01:
                risk = "CRITICAL" if unmet >= critical_kw else "MINOR"
                self.alerts.append(
                    f"[EMERGENCY: {risk}] {ts} - supply shortfall {unmet:.1f} kW | "
                    f"best source auto-selected, shedding non-critical load"
                )

            disaster = r.get("disaster", "NONE")
            if disaster not in ("NONE", "", None):
                self.disaster_warnings.append(
                    f"[DISASTER: {disaster}] {ts} - impact on energy system "
                    f"forecast, AI pre-charged battery + derates sources"
                )

            if r["solar_status"] == "UNAVAILABLE":
                self.alerts.append(
                    f"[ALERT] {ts} - SOLAR source problem detected, "
                    f"AI auto-switched to best available source"
                )
            if r["wind_status"] == "UNAVAILABLE":
                self.alerts.append(
                    f"[ALERT] {ts} - WIND source problem detected, "
                    f"AI auto-switched to best available source"
                )
            if r["hydro_status"] == "UNAVAILABLE":
                self.alerts.append(
                    f"[ALERT] {ts} - HYDRO source problem detected, "
                    f"AI auto-switched to best available source"
                )
            if r["generator_status"] == "UNAVAILABLE":
                self.alerts.append(
                    f"[ALERT] {ts} - GENERATOR source problem detected, "
                    f"AI auto-switched to renewable + battery"
                )

            if r["battery_soc_after_pct"] <= self.battery_low_soc:
                self.alerts.append(
                    f"[CAUTION] {ts} - battery SOC at {r['battery_soc_after_pct']:.1f}% "
                    f"(below {self.battery_low_soc:.0f}%), conserving to protect "
                    f"critical loads"
                )

            if r["generator_output_kw"] >= self.generator_capacity * 0.98:
                self.alerts.append(
                    f"[INFO] {ts} - generator at maximum output, "
                    f"consider reducing non-critical load"
                )

        return self.alerts

    def report(self):
        print("\n" + "=" * 58)
        print("EMERGENCY ENERGY SYSTEM - NOTIFICATIONS")
        print("=" * 58)
        if not self.alerts:
            print("  All sources healthy. No emergency situations.")
        for a in self.alerts:
            print(f"  {a}")
        self.total_unmet_kwh = round(self.total_unmet_kwh, 2)
        print(f"  Total unmet energy:         {self.total_unmet_kwh:9.2f} kWh")
        print("=" * 58)
        return self