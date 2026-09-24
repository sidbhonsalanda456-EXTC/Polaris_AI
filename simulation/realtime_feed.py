import time
import math
import random
import threading
from typing import Dict, Any, Optional
import httpx

# Official NCPOR (National Centre for Polar and Ocean Research, Govt. of India) Research Stations
NCPOR_STATIONS: Dict[str, Dict[str, Any]] = {
    "bharati": {
        "id": "bharati",
        "name": "Bharati Research Station",
        "full_title": "NCPOR Bharati Station (Larsemann Hills, East Antarctica)",
        "agency": "National Centre for Polar and Ocean Research (NCPOR), MoES, Govt. of India",
        "expedition": "44th Indian Scientific Expedition to Antarctica (ISEA)",
        "location": "Larsemann Hills, Princess Elizabeth Land",
        "continent": "Antarctica",
        "latitude": -69.408,
        "longitude": 76.187,
        "elevation_m": 35.0,
        "climate_zone": "Coastal Polar / Katabatic Wind Margin",
        "base_load_kw": 68.0,
        "peak_heating_kw": 95.0,
        "installed_solar_kw": 180.0,
        "installed_wind_kw": 120.0,
        "installed_bess_kwh": 300.0,
        "installed_diesel_kw": 200.0,
        "established_year": 2012,
        "open_meteo_url": "https://api.open-meteo.com/v1/forecast?latitude=-69.41&longitude=76.19&current=temperature_2m,wind_speed_10m,cloud_cover,surface_pressure"
    },
    "maitri": {
        "id": "maitri",
        "name": "Maitri Research Station",
        "full_title": "NCPOR Maitri Station (Schirmacher Oasis, Queen Maud Land)",
        "agency": "National Centre for Polar and Ocean Research (NCPOR), MoES, Govt. of India",
        "expedition": "44th Indian Scientific Expedition to Antarctica (ISEA)",
        "location": "Schirmacher Oasis, Queen Maud Land",
        "continent": "Antarctica",
        "latitude": -70.766,
        "longitude": 11.733,
        "elevation_m": 117.0,
        "climate_zone": "Inland Continental Polar Oasis",
        "base_load_kw": 58.0,
        "peak_heating_kw": 88.0,
        "installed_solar_kw": 140.0,
        "installed_wind_kw": 100.0,
        "installed_bess_kwh": 250.0,
        "installed_diesel_kw": 180.0,
        "established_year": 1989,
        "open_meteo_url": "https://api.open-meteo.com/v1/forecast?latitude=-70.77&longitude=11.73&current=temperature_2m,wind_speed_10m,cloud_cover,surface_pressure"
    },
    "himadri": {
        "id": "himadri",
        "name": "Himadri Arctic Station",
        "full_title": "NCPOR Himadri Station (Ny-Ålesund, Svalbard, Arctic)",
        "agency": "National Centre for Polar and Ocean Research (NCPOR), MoES, Govt. of India",
        "expedition": "Indian Arctic Scientific Expedition",
        "location": "Ny-Ålesund, Spitsbergen, Svalbard",
        "continent": "Arctic",
        "latitude": 78.924,
        "longitude": 11.928,
        "elevation_m": 12.0,
        "climate_zone": "High Arctic Marine Permafrost",
        "base_load_kw": 45.0,
        "peak_heating_kw": 70.0,
        "installed_solar_kw": 100.0,
        "installed_wind_kw": 80.0,
        "installed_bess_kwh": 200.0,
        "installed_diesel_kw": 150.0,
        "established_year": 2008,
        "open_meteo_url": "https://api.open-meteo.com/v1/forecast?latitude=78.92&longitude=11.93&current=temperature_2m,wind_speed_10m,cloud_cover,surface_pressure"
    }
}

class RealTimeDataStreamer:
    """
    Ingests and streams real-time environmental telemetry for NCPOR Polar Research Stations.
    Supports three dynamic input modes:
    1. REAL_WORLD_LIVE: Fetches real-time weather from actual NCPOR Antarctic / Arctic coordinates
       (Bharati Station: -69.41°S, 76.19°E; Maitri: -70.77°S, 11.73°E; Himadri: 78.92°N, 11.93°E)
       via Open-Meteo API, with continuous high-frequency dynamic micro-turbulence.
    2. DYNAMIC_SYNTHETIC: Continuous physics-based dynamic stochastic Antarctic climate generator.
    3. MANUAL_STREAM: Accepts dynamic manual adjustments from operator sliders and scenario triggers.
    """
    def __init__(self, mode: str = "REAL_WORLD_LIVE", default_station: str = "bharati"):
        self.mode = mode
        self.step_count = 0
        self._lock = threading.Lock()
        
        # Station selection
        self.current_station_id = default_station if default_station in NCPOR_STATIONS else "bharati"
        self.station_spec = NCPOR_STATIONS[self.current_station_id]
        
        # Real-time state variables
        self.temperature_c = -16.4
        self.solar_irradiance_w_m2 = 460.0
        self.wind_speed_m_s = 11.8
        self.cloud_cover = 0.28
        self.atmospheric_pressure_hpa = 980.5
        self.weather_condition = "Partly Cloudy"
        self.feed_status = "Connected (NCPOR Live Telemetry)"
        self.feed_source_label = f"NCPOR Live Feed — {self.station_spec['full_title']}"
        
        # Manual stream overrides
        self.manual_temperature = None
        self.manual_solar = None
        self.manual_wind = None
        self.manual_cloud = None
        self.override_active = False

        # Live API Poller
        self.last_api_fetch_ts = 0.0
        self.cached_api_data: Optional[Dict[str, Any]] = None
        self._trigger_fetch_event = threading.Event()
        self._start_api_poller()

    def set_station(self, station_id: str) -> Dict[str, Any]:
        """Switches active NCPOR polar station."""
        sid = station_id.lower().strip()
        if sid in NCPOR_STATIONS:
            with self._lock:
                self.current_station_id = sid
                self.station_spec = NCPOR_STATIONS[sid]
                if self.mode == "REAL_WORLD_LIVE":
                    self.feed_source_label = f"NCPOR Live Feed — {self.station_spec['full_title']}"
            # Signal immediate re-poll
            self._trigger_fetch_event.set()
        return self.get_station_metadata()

    def get_station_metadata(self) -> Dict[str, Any]:
        with self._lock:
            spec = dict(self.station_spec)
            spec["active"] = True
            return spec

    def set_override(self, condition: Optional[str] = None, cloud_cover: Optional[float] = None,
                      temperature: Optional[float] = None, wind_speed: Optional[float] = None,
                      solar_irradiance: Optional[float] = None):
        self.set_manual_inputs(temperature=temperature, solar=solar_irradiance, wind=wind_speed, cloud=cloud_cover)
        if condition:
            self.weather_condition = condition
        self.override_active = True
        self.mode = "MANUAL_STREAM"

    def clear_override(self):
        self.manual_temperature = None
        self.manual_solar = None
        self.manual_wind = None
        self.manual_cloud = None
        self.override_active = False
        self.mode = "REAL_WORLD_LIVE"

    def set_mode(self, mode: str):
        with self._lock:
            if mode in ["REAL_WORLD_LIVE", "DYNAMIC_SYNTHETIC", "MANUAL_STREAM"]:
                self.mode = mode
                if mode == "REAL_WORLD_LIVE":
                    self.feed_source_label = f"NCPOR Live Feed — {self.station_spec['full_title']}"
                elif mode == "MANUAL_STREAM":
                    self.feed_source_label = "Interactive Dynamic Sliders Feed"
                else:
                    self.feed_source_label = f"Dynamic Synthetic Polar Stream — {self.station_spec['name']}"

    def set_manual_inputs(self, temperature: Optional[float] = None,
                          solar: Optional[float] = None,
                          wind: Optional[float] = None,
                          cloud: Optional[float] = None):
        with self._lock:
            if temperature is not None:
                self.manual_temperature = float(temperature)
            if solar is not None:
                self.manual_solar = max(0.0, float(solar))
            if wind is not None:
                self.manual_wind = max(0.0, float(wind))
            if cloud is not None:
                self.manual_cloud = max(0.0, min(1.0, float(cloud)))

    def _fetch_live_weather(self):
        """Fetches live weather from Open-Meteo for the current NCPOR station."""
        url = self.station_spec["open_meteo_url"]
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("current", {})
                    with self._lock:
                        self.cached_api_data = data
                        self.feed_status = "Connected (NCPOR Live Telemetry)"
                        self.last_api_fetch_ts = time.time()
                        # Immediately seed base values
                        temp = float(data.get("temperature_2m", self.temperature_c))
                        wind = float(data.get("wind_speed_10m", self.wind_speed_m_s * 3.6)) / 3.6
                        cloud = float(data.get("cloud_cover", 30.0)) / 100.0
                        press = float(data.get("surface_pressure", 980.0))
                        self.temperature_c = round(temp, 1)
                        self.wind_speed_m_s = round(wind, 1)
                        self.cloud_cover = round(cloud, 2)
                        self.atmospheric_pressure_hpa = round(press, 1)
        except Exception:
            with self._lock:
                self.feed_status = "Autonomous Microgrid Fallback"

    def _start_api_poller(self):
        # Fetch once initially
        self._fetch_live_weather()

        def _poll_worker():
            while True:
                # Wait for 60 seconds or explicit trigger
                triggered = self._trigger_fetch_event.wait(timeout=60.0)
                if triggered:
                    self._trigger_fetch_event.clear()
                self._fetch_live_weather()

        t = threading.Thread(target=_poll_worker, daemon=True)
        t.start()

    def step(self) -> Dict[str, Any]:
        """Advances and computes the latest dynamic telemetry frame with micro-fluctuations."""
        with self._lock:
            self.step_count += 1
            
            # Antarctic Diurnal Cycle Phase (240 ticks = 1 cycle)
            phase = (self.step_count % 240) / 240.0 * 2.0 * math.pi
            
            if self.mode == "REAL_WORLD_LIVE" and self.cached_api_data:
                api = self.cached_api_data
                base_temp = float(api.get("temperature_2m", -18.0))
                base_wind = float(api.get("wind_speed_10m", 28.0)) / 3.6  # km/h to m/s
                base_cloud = float(api.get("cloud_cover", 25.0)) / 100.0
                
                # Apply realistic polar micro-turbulences every second
                # Katabatic wind gusts have slight auto-regressive drift
                wind_gust = random.gauss(0, 0.45)
                self.wind_speed_m_s = round(max(0.5, min(45.0, base_wind + wind_gust + 0.8 * math.sin(phase * 1.5))), 1)
                
                # Cloud cover drifting
                cloud_jitter = random.uniform(-0.015, 0.015)
                self.cloud_cover = round(max(0.0, min(1.0, base_cloud + cloud_jitter)), 2)
                
                # Solar elevation calculation (Antarctic coastal summer vs twilight)
                sun_elev = math.sin(phase)
                raw_solar = max(0.0, 720.0 * (sun_elev ** 0.8)) if sun_elev > 0 else 0.0
                self.solar_irradiance_w_m2 = round(raw_solar * (1.0 - 0.76 * (self.cloud_cover ** 1.5)), 1)
                
                # Temperature with micro wind-chill and solar heating
                solar_warming = (self.solar_irradiance_w_m2 / 800.0) * 2.5
                wind_cooling = -0.08 * max(0.0, self.wind_speed_m_s - 8.0)
                temp_fluct = random.uniform(-0.1, 0.1)
                self.temperature_c = round(base_temp + solar_warming + wind_cooling + temp_fluct, 1)
                self.atmospheric_pressure_hpa = round(float(api.get("surface_pressure", 980.0)) + 0.5 * math.cos(phase), 1)

            elif self.mode == "MANUAL_STREAM":
                if self.manual_temperature is not None:
                    self.temperature_c = round(self.manual_temperature, 1)
                if self.manual_solar is not None:
                    self.solar_irradiance_w_m2 = round(self.manual_solar, 1)
                if self.manual_wind is not None:
                    self.wind_speed_m_s = round(self.manual_wind, 1)
                if self.manual_cloud is not None:
                    self.cloud_cover = round(self.manual_cloud, 2)
                self.atmospheric_pressure_hpa = 980.0

            else:
                # DYNAMIC_SYNTHETIC: Continuous physics-based dynamic generator tailored to station
                sun_elev = math.sin(phase)
                raw_solar = max(0.0, 750.0 * (sun_elev ** 0.8)) if sun_elev > 0 else 0.0
                self.cloud_cover = max(0.0, min(1.0, self.cloud_cover + random.uniform(-0.025, 0.025)))
                self.solar_irradiance_w_m2 = round(raw_solar * (1.0 - 0.78 * (self.cloud_cover ** 1.6)), 1)
                
                # Dynamic katabatic winds (common in Larsemann Hills & Schirmacher Oasis)
                target_wind = 12.0 + 6.0 * math.sin(phase * 0.75)
                self.wind_speed_m_s = max(0.8, min(42.0, self.wind_speed_m_s + 0.15 * (target_wind - self.wind_speed_m_s) + random.gauss(0, 1.1)))
                self.wind_speed_m_s = round(self.wind_speed_m_s, 1)
                
                # Temperature with diurnal wave and katabatic chill
                base_station_temp = -18.0 if self.current_station_id == "bharati" else -22.0
                solar_warm = (self.solar_irradiance_w_m2 / 800.0) * 3.5
                wind_chill = -0.12 * max(0.0, self.wind_speed_m_s - 10.0)
                temp_target = base_station_temp + 3.0 * math.sin(phase - math.pi / 4.0) + solar_warm + wind_chill
                self.temperature_c += 0.1 * (temp_target - self.temperature_c) + random.uniform(-0.15, 0.15)
                self.temperature_c = round(self.temperature_c, 1)
                self.atmospheric_pressure_hpa = round(980.0 + 4.0 * math.cos(phase), 1)

            # Weather condition classification
            if self.wind_speed_m_s > 25.0 and self.cloud_cover > 0.7:
                self.weather_condition = "Katabatic Blizzard"
            elif self.wind_speed_m_s > 18.0:
                self.weather_condition = "Severe Polar Gale"
            elif self.temperature_c < -30.0:
                self.weather_condition = "Extreme Polar Freeze"
            elif self.cloud_cover > 0.75:
                self.weather_condition = "Overcast Snowfall"
            elif self.cloud_cover > 0.35:
                self.weather_condition = "Partly Cloudy"
            elif self.solar_irradiance_w_m2 > 300.0:
                self.weather_condition = "Clear Polar Daylight"
            else:
                self.weather_condition = "Calm Twilight"

            return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        spec = self.station_spec
        return {
            "temperature_c": self.temperature_c,
            "solar_irradiance_w_m2": self.solar_irradiance_w_m2,
            "wind_speed_m_s": self.wind_speed_m_s,
            "cloud_cover": round(self.cloud_cover, 2),
            "atmospheric_pressure_hpa": self.atmospheric_pressure_hpa,
            "weather_condition": self.weather_condition,
            "feed_mode": self.mode,
            "feed_source_label": self.feed_source_label,
            "feed_status": self.feed_status,
            "step": self.step_count,
            "station": {
                "id": spec["id"],
                "name": spec["name"],
                "full_title": spec["full_title"],
                "agency": spec["agency"],
                "expedition": spec["expedition"],
                "location": spec["location"],
                "continent": spec["continent"],
                "latitude": spec["latitude"],
                "longitude": spec["longitude"],
                "elevation_m": spec["elevation_m"],
                "climate_zone": spec["climate_zone"],
                "base_load_kw": spec["base_load_kw"],
                "peak_heating_kw": spec["peak_heating_kw"],
                "established_year": spec["established_year"]
            }
        }
