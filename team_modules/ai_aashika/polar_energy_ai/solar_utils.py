import math
from datetime import datetime, timedelta


def solar_declination_deg(day_of_year):
    """Solar declination (radians -> degrees) for a day of year, NOAA-style formula.
    Negative in the southern-hemisphere summer (e.g. -23.4 deg around Dec 21),
    positive around Jun 21. This drives polar day/night automatically.
    """
    g = 2 * math.pi / 365 * (day_of_year - 1)
    dec = (0.006918
           - 0.399912 * math.cos(g)
           + 0.070257 * math.sin(g)
           - 0.006758 * math.cos(2 * g)
           + 0.000907 * math.sin(2 * g)
           - 0.002697 * math.cos(3 * g)
           + 0.00148 * math.sin(3 * g))
    return math.degrees(dec)


def hour_angle_deg(local_hour):
    """Hour angle (degrees) from local clock time. 0 deg = local solar noon (12:00)."""
    return 15.0 * (local_hour - 12.0)


def solar_elevation_deg(dt, latitude_deg):
    """True solar altitude above the horizon (deg) at a datetime (any tz-aware/naive
    datetime; only the local clock hour + day-of-year matter here).
    Negative = sun below horizon.
    """
    doy = dt.timetuple().tm_yday
    dec = math.radians(solar_declination_deg(doy))
    ha = math.radians(hour_angle_deg(dt.hour + dt.minute / 60))
    lat = math.radians(latitude_deg)
    sin_alt = (math.sin(lat) * math.sin(dec)
               + math.cos(lat) * math.cos(dec) * math.cos(ha))
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def solar_elevation_doy_deg(day_of_year, hour, latitude_deg):
    """Solar elevation at an (hour, day_of_year) without a real timestamp."""
    base = datetime(2000, 1, 1) + timedelta(days=day_of_year - 1)
    dt = base.replace(hour=int(hour))
    return solar_elevation_deg(dt, latitude_deg)


def sun_is_up(datetime_aware, latitude_deg, threshold_deg=0.0):
    """True while the sun is actually above the horizon - the auto-shifting
    daylight window that replaces the fixed 08:00-16:00 rule."""
    return solar_elevation_deg(datetime_aware, latitude_deg) > threshold_deg


def solar_irradiance_base(elevation_deg, cloud_cover_pct):
    """Clear-sky-ish irradiance scaled by sin(elevation) and cloud cover (W/m2)."""
    curv = max(0.0, math.sin(math.radians(elevation_deg)))
    if curv <= 0.001:
        return 0.0
    return max(0.0, curv * 900 * (1 - max(0, min(100, cloud_cover_pct)) / 150))