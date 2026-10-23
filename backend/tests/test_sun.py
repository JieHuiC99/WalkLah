from datetime import datetime

import pytest

from app.sun import MALAYSIA, sun_position

UM = (3.118, 101.655)


def at(month, day, hour, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=MALAYSIA)


def test_night_and_day():
    assert not sun_position(at(3, 20, 5, 0), *UM).daylight
    assert sun_position(at(3, 20, 13, 0), *UM).daylight
    assert not sun_position(at(3, 20, 21, 0), *UM).daylight


def test_equinox_noon_is_nearly_overhead():
    # Solar noon in KL is about 13:15 local time; near the equinox the sun is almost overhead.
    best = max(sun_position(at(3, 20, 13, m), *UM).altitude for m in range(0, 60, 5))
    assert best > 85


def test_morning_sun_in_the_east_and_afternoon_in_the_west():
    morning = sun_position(at(3, 20, 9, 0), *UM)
    afternoon = sun_position(at(3, 20, 17, 0), *UM)
    # Solar noon is ~13:15 local, so 09:00 is ~4.25 h before it (≈ 25° up) and 17:00 ~3.75 h after (≈ 33°).
    assert 80 < morning.azimuth < 100 and 20 < morning.altitude < 35
    assert 260 < afternoon.azimuth < 280 and 25 < afternoon.altitude < 40


def test_june_noon_sun_is_to_the_north():
    noon = sun_position(at(6, 21, 13, 15), *UM)
    assert noon.azimuth > 300 or noon.azimuth < 60
    assert noon.altitude == pytest.approx(69.6, abs=1.5)  # 90 - (23.44 - 3.12)


def test_naive_datetime_is_malaysia_time():
    naive = datetime(2026, 3, 20, 9, 0)
    assert sun_position(naive, *UM) == sun_position(at(3, 20, 9, 0), *UM)
