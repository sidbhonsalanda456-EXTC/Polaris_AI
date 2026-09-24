import math
import random
from typing import Dict, Any, Optional

class PolarWeatherModel:
    """
    Simulates dynamic Arctic/Antarctic weather conditions.
    Includes diurnal cycles, random fluctuations, cloud attenuation,
    wind gusts, blizzard/storm transitions, and manual scenario overrides.
    """
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.step_count = 0
        
        # Base polar climate parameters
        self.base_temperature = -25.0  # Celsius (-45 to -10 typical)
        self.temperature = self.base_temperature
        self.cloud_cover = 0.25         # 0.0 (clear) to 1.0 (thick overcast)
        self.wind_speed = 8.5           # m/s (0 to 35+)
        self.solar_irradiance = 450.0   # W/m2 (0 to 800)
        self.visibility = 35.0          # km (0.1 to 50)
        self.condition = "Clear"
        
        # Override flags for demo / manual scenario injection
        self.override_active = False
        self.override_params: Dict[str, Any] = {}

    def set_override(self, condition: Optional[str] = None, cloud_cover: Optional[float] = None,
                     temperature: Optional[float] = None, wind_speed: Optional[float] = None,
                     solar_irradiance: Optional[float] = None):
        """Allows demo or manual injection of specific weather phenomena."""
        self.override_active = True
        if condition is not None:
            self.override_params['condition'] = condition
        if cloud_cover is not None:
            self.override_params['cloud_cover'] = max(0.0, min(1.0, cloud_cover))
        if temperature is not None:
            self.override_params['temperature'] = temperature
        if wind_speed is not None:
            self.override_params['wind_speed'] = max(0.0, wind_speed)
        if solar_irradiance is not None:
            self.override_params['solar_irradiance'] = max(0.0, solar_irradiance)

    def clear_override(self):
        self.override_active = False
        self.override_params.clear()

    def step(self) -> Dict[str, Any]:
        """Advances weather simulation by one time step (nominal 1 minute per tick)."""
        self.step_count += 1
        
        # Polar diurnal cycle (24h period, nominal 1440 steps = 1 day, or 120 steps = fast day)
        # We use a 240-step cycle for visually active demonstration
        cycle_phase = (self.step_count % 240) / 240.0 * 2.0 * math.pi
        
        # Solar elevation angle model
        # Polar summer: sun stays above horizon but dips; polar winter: long darkness
        sun_elevation = math.sin(cycle_phase)
        if sun_elevation > 0:
            clear_sky_irradiance = 700.0 * (sun_elevation ** 0.8)
        else:
            clear_sky_irradiance = 0.0  # Polar twilight/night
            
        # Cloud cover random walk
        cloud_delta = random.uniform(-0.04, 0.04)
        self.cloud_cover = max(0.0, min(1.0, self.cloud_cover + cloud_delta))
        
        # Attenuate solar irradiance by clouds: attenuation factor ~ (1 - 0.75 * cloud_cover^2)
        effective_solar = clear_sky_irradiance * max(0.05, 1.0 - 0.80 * (self.cloud_cover ** 1.8))
        self.solar_irradiance = round(effective_solar, 1)
        
        # Wind speed dynamics (Ornstein-Uhlenbeck style mean-reverting + gusts)
        target_wind = 9.0 + 4.0 * math.sin(cycle_phase * 0.5)
        wind_noise = random.gauss(0, 1.5)
        self.wind_speed = max(0.5, min(40.0, self.wind_speed + 0.15 * (target_wind - self.wind_speed) + wind_noise))
        self.wind_speed = round(self.wind_speed, 1)
        
        # Temperature dynamics (solar heating + wind chill + random walk)
        solar_warming = (self.solar_irradiance / 800.0) * 4.0
        wind_chill_effect = -0.1 * max(0.0, self.wind_speed - 10.0)
        temp_target = self.base_temperature + 3.0 * math.sin(cycle_phase - math.pi / 4.0) + solar_warming + wind_chill_effect
        self.temperature += 0.1 * (temp_target - self.temperature) + random.uniform(-0.2, 0.2)
        self.temperature = round(self.temperature, 1)
        
        # Classify weather condition
        if self.wind_speed > 22.0 and self.cloud_cover > 0.7:
            self.condition = "Polar Blizzard"
            self.visibility = round(max(0.2, 5.0 - (self.wind_speed - 22.0) * 0.4), 1)
        elif self.wind_speed > 18.0:
            self.condition = "High Wind"
            self.visibility = round(max(2.0, 20.0 - self.wind_speed * 0.5), 1)
        elif self.cloud_cover > 0.75:
            self.condition = "Overcast"
            self.visibility = round(max(5.0, 30.0 - self.cloud_cover * 15.0), 1)
        elif self.cloud_cover > 0.35:
            self.condition = "Partly Cloudy"
            self.visibility = round(35.0 + random.uniform(-3, 3), 1)
        else:
            self.condition = "Clear"
            self.visibility = round(45.0 + random.uniform(-2, 2), 1)
            
        # Apply overrides if active
        if self.override_active:
            if 'cloud_cover' in self.override_params:
                self.cloud_cover = self.override_params['cloud_cover']
            if 'temperature' in self.override_params:
                self.temperature = self.override_params['temperature']
            if 'wind_speed' in self.override_params:
                self.wind_speed = self.override_params['wind_speed']
            if 'solar_irradiance' in self.override_params:
                self.solar_irradiance = self.override_params['solar_irradiance']
            if 'condition' in self.override_params:
                self.condition = self.override_params['condition']

        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        return {
            "step": self.step_count,
            "temperature": self.temperature,
            "solar_irradiance": self.solar_irradiance,
            "wind_speed": self.wind_speed,
            "cloud_cover": round(self.cloud_cover, 2),
            "visibility": self.visibility,
            "condition": self.condition
        }
