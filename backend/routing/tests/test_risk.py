import pytest

from routing.risk import Risk, assess, continuous_score, rain_level, snow_level, wind_level


@pytest.mark.parametrize("mph,expected", [
    (0, Risk.LOW), (24.9, Risk.LOW),
    (25, Risk.MODERATE), (34.9, Risk.MODERATE),
    (35, Risk.HIGH), (44.9, Risk.HIGH),
    (45, Risk.SEVERE), (54.9, Risk.SEVERE),
    (55, Risk.NO_TRAVEL), (80, Risk.NO_TRAVEL),
])
def test_wind_bands(mph, expected):
    assert wind_level(mph) == expected


@pytest.mark.parametrize("rate,expected", [
    (0, Risk.LOW), (0.09, Risk.LOW),
    (0.10, Risk.MODERATE), (0.24, Risk.MODERATE),
    (0.25, Risk.HIGH), (0.49, Risk.HIGH),
    (0.50, Risk.SEVERE), (1.00, Risk.SEVERE),
    (1.01, Risk.NO_TRAVEL),
])
def test_rain_bands(rate, expected):
    assert rain_level(rate) == expected


@pytest.mark.parametrize("rate,expected", [
    (0.4, Risk.LOW), (0.5, Risk.MODERATE), (1.0, Risk.HIGH),
    (2.0, Risk.SEVERE), (3.0, Risk.SEVERE), (3.1, Risk.NO_TRAVEL),
])
def test_snow_bands(rate, expected):
    assert snow_level(rate) == expected


def test_worst_condition_wins():
    a = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0, load_lb=10_000)
    assert a.level == Risk.HIGH
    assert any("Rain" in r for r in a.reasons)


class TestLoadRules:
    def test_55_mph_is_no_travel_for_light_load(self):
        assert assess(55, 0, 0, 5_000).level == Risk.NO_TRAVEL

    def test_severe_wind_heavy_load_is_no_travel(self):
        a = assess(48, 0, 0, 30_001)
        assert a.level == Risk.NO_TRAVEL
        assert any("30,000" in r for r in a.reasons)

    def test_severe_wind_at_exactly_30k_stays_severe(self):
        assert assess(48, 0, 0, 30_000).level == Risk.SEVERE

    def test_high_wind_very_heavy_load_is_severe(self):
        assert assess(40, 0, 0, 40_001).level == Risk.SEVERE

    def test_high_wind_at_exactly_40k_stays_high(self):
        assert assess(40, 0, 0, 40_000).level == Risk.HIGH

    def test_load_rule_never_lowers_level(self):
        # 40 mph + heavy load bumps wind to Severe, but heavy rain is already No Travel
        assert assess(40, 1.5, 0, 45_000).level == Risk.NO_TRAVEL

    def test_moderate_wind_heavy_load_unchanged(self):
        assert assess(30, 0, 0, 79_000).level == Risk.MODERATE


def test_continuous_score_sits_inside_band():
    assert continuous_score(30, 0, 0, Risk.MODERATE) == pytest.approx(1.5)
    # load rule pushed the level up, shading follows
    assert continuous_score(40, 0, 0, Risk.SEVERE) == 3.0
    assert continuous_score(90, 0, 0, Risk.NO_TRAVEL) == 4.0
