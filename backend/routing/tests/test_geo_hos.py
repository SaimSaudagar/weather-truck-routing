import pytest

from routing import geo, hos


def test_haversine_known_distance():
    # Dallas -> Chicago, roughly 800 miles as the crow flies
    d = geo.haversine_mi((-96.797, 32.777), (-87.623, 41.881))
    assert 790 < d < 810


def test_sample_distances_includes_start_and_end():
    assert geo.sample_distances(60, 25) == [0, 25, 50, 60]


def test_sample_distances_drops_mark_right_before_end():
    # 50 is only 2 miles from the end, so it's merged into the destination point
    assert geo.sample_distances(52, 25) == [0, 25, 52]


def test_point_at_and_interpolate():
    line = [(0, 0), (0, 1), (0, 2)]
    cum = geo.cumulative_miles(line)
    mid = geo.point_at(line, cum, cum[-1] / 2)
    assert mid == pytest.approx((0, 1))
    assert geo.interpolate(cum, [0, 100, 200], cum[-1] * 0.75) == pytest.approx(150)


def test_overlap_ratio():
    a = [(0, 0), (0, 1)]
    b = [(0, 0), (0, 0.5), (0, 1)]
    far = [(2, 0), (2, 1)]
    assert geo.overlap_ratio(a, b) == 1.0
    assert geo.overlap_ratio(a, far) == 0.0


H = 3600


@pytest.mark.parametrize("drive,expected", [
    (5 * H, 5 * H),                         # short trip, nothing added
    (9 * H, 9.5 * H),                       # 30 min break after hour 8
    (11 * H, 11.5 * H),                     # ends right at the 11h limit, no rest needed
    (12 * H, 12 * H + 0.5 * H + 10 * H),    # rest after the first 11h
    (20 * H, 20 * H + 0.5 * H + 10 * H + 0.5 * H),  # second shift also passes 8h
])
def test_hos_elapsed(drive, expected):
    assert hos.elapsed_for_drive(drive) == expected


def test_hos_disabled():
    assert hos.elapsed_for_drive(20 * H, enabled=False) == 20 * H
