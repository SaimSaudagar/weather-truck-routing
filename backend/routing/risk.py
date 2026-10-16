"""
Risk classification for a single checkpoint.

Thresholds come straight from the assignment table. The table has shared
boundaries (e.g. rain 0.25 shows up in both Moderate and High), so I treat
each band as lower-bound inclusive: 0.25 in/hr is High, 35 mph is High.
The only exception is the top band for rain/snow which is written as
">1.00" / ">3.0", so exactly 1.00 in/hr rain is still Severe.
"""
from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self):
        return self.name.replace("_", " ").title()

    @property
    def key(self):
        return self.name.lower()


# (upper bound, level) pairs. A value lands in the first band where value < bound.
WIND_BANDS = [(25, Risk.LOW), (35, Risk.MODERATE), (45, Risk.HIGH), (55, Risk.SEVERE)]
RAIN_BANDS = [(0.10, Risk.LOW), (0.25, Risk.MODERATE), (0.50, Risk.HIGH)]
SNOW_BANDS = [(0.5, Risk.LOW), (1.0, Risk.MODERATE), (2.0, Risk.HIGH)]

RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_NO_TRAVEL_ABOVE = 3.0


def _band(value, bands, fallback):
    for upper, level in bands:
        if value < upper:
            return level
    return fallback


def wind_level(mph):
    return _band(mph, WIND_BANDS, Risk.NO_TRAVEL)


def rain_level(in_per_hr):
    if in_per_hr > RAIN_NO_TRAVEL_ABOVE:
        return Risk.NO_TRAVEL
    return _band(in_per_hr, RAIN_BANDS, Risk.SEVERE)


def snow_level(in_per_hr):
    if in_per_hr > SNOW_NO_TRAVEL_ABOVE:
        return Risk.NO_TRAVEL
    return _band(in_per_hr, SNOW_BANDS, Risk.SEVERE)


def apply_load_rules(wind_mph, load_lb, level):
    """Heavier trucks get bumped up in strong wind. Returns (level, reason or None)."""
    if wind_mph >= 55:
        return Risk.NO_TRAVEL, "Wind ≥55 mph: no travel for any load"
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return Risk.NO_TRAVEL, "Wind 45–54 mph with load >30,000 lb"
    if 35 <= wind_mph < 45 and load_lb > 40_000 and level < Risk.SEVERE:
        return Risk.SEVERE, "Wind 35–44 mph with load >40,000 lb"
    return level, None


@dataclass
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {
            "level": self.level.key,
            "score": int(self.level),
            "wind": self.wind.key,
            "rain": self.rain.key,
            "snow": self.snow.key,
            "reasons": self.reasons,
        }


def assess(wind_mph, rain_in_hr, snow_in_hr, load_lb):
    w, r, s = wind_level(wind_mph), rain_level(rain_in_hr), snow_level(snow_in_hr)
    level = max(w, r, s)

    reasons = []
    for name, lvl, value, unit in (
        ("Wind", w, wind_mph, "mph"),
        ("Rain", r, rain_in_hr, "in/hr"),
        ("Snow", s, snow_in_hr, "in/hr"),
    ):
        if lvl == level and lvl > Risk.LOW:
            reasons.append(f"{name} {value:g} {unit} → {lvl.label}")

    adjusted, load_reason = apply_load_rules(wind_mph, load_lb, level)
    if load_reason and adjusted > level:
        reasons.append(f"{load_reason} → {adjusted.label}")
    level = max(level, adjusted)

    return Assessment(level=level, wind=w, rain=r, snow=s, reasons=reasons)


# Band edges for a continuous 0..4 score, used only to shade the heatmap.
# The last edge is an arbitrary "well past No Travel" point to cap the scale.
_WIND_EDGES = [0, 25, 35, 45, 55, 65]
_RAIN_EDGES = [0, 0.10, 0.25, 0.50, 1.00, 1.50]
_SNOW_EDGES = [0, 0.5, 1.0, 2.0, 3.0, 4.0]


def _position(value, edges):
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        if value < hi:
            return i + (value - lo) / (hi - lo)
    return float(len(edges) - 2)


def continuous_score(wind_mph, rain_in_hr, snow_in_hr, level):
    """Where in the scale a reading sits, e.g. 30 mph wind -> 1.5. Never below `level`."""
    raw = max(
        _position(wind_mph, _WIND_EDGES),
        _position(rain_in_hr, _RAIN_EDGES),
        _position(snow_in_hr, _SNOW_EDGES),
    )
    return min(4.0, max(raw, float(level)))
