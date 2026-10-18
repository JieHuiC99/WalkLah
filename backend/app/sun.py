"""Sun position (NOAA solar calculator equations).

Accurate to well under a degree for 1950-2050, which is plenty for shadows.
Refraction is ignored, so near sunrise/sunset the sun is treated as slightly
lower than it looks.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MALAYSIA = ZoneInfo("Asia/Kuala_Lumpur")


@dataclass(frozen=True)
class SunPosition:
    altitude: float  # degrees above the horizon (negative = night)
    azimuth: float  # degrees clockwise from north

    @property
    def daylight(self) -> bool:
        return self.altitude > 0


def _julian_day(dt: datetime) -> float:
    dt = dt.astimezone(timezone.utc)
    year, month = dt.year, dt.month
    day = dt.day + (dt.hour + (dt.minute + dt.second / 60) / 60) / 24
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    return int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5


def sun_position(when: datetime, lat: float, lon: float) -> SunPosition:
    """Altitude/azimuth of the sun at `when` (timezone-aware) for a WGS84 point."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=MALAYSIA)
    jc = (_julian_day(when) - 2451545.0) / 36525.0
    rad, deg = math.radians, math.degrees

    mean_long = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    mean_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    centre = (math.sin(rad(mean_anom)) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
              + math.sin(rad(2 * mean_anom)) * (0.019993 - 0.000101 * jc)
              + math.sin(rad(3 * mean_anom)) * 0.000289)
    true_long = mean_long + centre
    omega = 125.04 - 1934.136 * jc
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(rad(omega))
    mean_obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = mean_obliq + 0.00256 * math.cos(rad(omega))
    declination = deg(math.asin(math.sin(rad(obliq)) * math.sin(rad(apparent_long))))

    y = math.tan(rad(obliq / 2)) ** 2
    eq_time = 4 * deg(
        y * math.sin(2 * rad(mean_long))
        - 2 * ecc * math.sin(rad(mean_anom))
        + 4 * ecc * y * math.sin(rad(mean_anom)) * math.cos(2 * rad(mean_long))
        - 0.5 * y * y * math.sin(4 * rad(mean_long))
        - 1.25 * ecc * ecc * math.sin(2 * rad(mean_anom))
    )

    utc = when.astimezone(timezone.utc)
    minutes = utc.hour * 60 + utc.minute + utc.second / 60
    true_solar = (minutes + eq_time + 4 * lon) % 1440
    hour_angle = true_solar / 4 - 180 if true_solar / 4 >= 0 else true_solar / 4 + 180

    cos_zenith = (math.sin(rad(lat)) * math.sin(rad(declination))
                  + math.cos(rad(lat)) * math.cos(rad(declination)) * math.cos(rad(hour_angle)))
    zenith = deg(math.acos(max(-1.0, min(1.0, cos_zenith))))
    altitude = 90 - zenith

    denom = math.cos(rad(lat)) * math.sin(rad(zenith))
    if abs(denom) < 1e-9:
        azimuth = 180.0
    else:
        cos_az = ((math.sin(rad(lat)) * math.cos(rad(zenith))) - math.sin(rad(declination))) / denom
        az = deg(math.acos(max(-1.0, min(1.0, cos_az))))
        azimuth = (az + 180) % 360 if hour_angle > 0 else (540 - az) % 360
    return SunPosition(altitude=round(altitude, 3), azimuth=round(azimuth, 3))
