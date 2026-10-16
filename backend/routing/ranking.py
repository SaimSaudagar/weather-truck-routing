"""
Route ordering, following the brief:

    1. fewest Severe miles
    2. fewest High miles
    3. lowest average risk
    4. shortest travel time

Any No Travel mileage is checked before all of that. The brief doesn't list
it, but a route that crosses a no-travel zone can't be the safe choice no
matter how short it is.

Miles are compared to the nearest mile and average risk to one decimal.
Without that, 0.01 of average risk would always beat an hour of driving
and travel time would never matter.
"""
from .risk import Risk

CRITERIA = [
    # (label, getter, how to print the value)
    ("No Travel miles", lambda r: round(r["risk_miles"]["no_travel"]), "{:.0f} mi"),
    ("Severe miles", lambda r: round(r["risk_miles"]["severe"]), "{:.0f} mi"),
    ("High miles", lambda r: round(r["risk_miles"]["high"]), "{:.0f} mi"),
    ("average risk", lambda r: round(r["avg_risk"], 1), "{:.1f}"),
    ("travel time", lambda r: round(r["trip_s"] / 60), None),
]


def sort_key(route):
    return tuple(get(route) for _, get, _ in CRITERIA)


def _fmt_minutes(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m"


def explain(winner, other):
    """First criterion where the winner beats `other`, as a sentence."""
    for label, get, fmt in CRITERIA:
        a, b = get(winner), get(other)
        if a == b:
            continue
        if fmt:
            va, vb = fmt.format(a), fmt.format(b)
        else:
            va, vb = _fmt_minutes(a), _fmt_minutes(b)
        word = "shorter" if label == "travel time" else "lower" if label == "average risk" else "fewer"
        return f"{word} {label} than {other['name']} ({va} vs {vb})"
    return f"equal to {other['name']} on every criterion"


def rank(routes):
    ordered = sorted(routes, key=sort_key)
    for i, r in enumerate(ordered, start=1):
        r["rank"] = i
        r["recommended"] = i == 1

    best = ordered[0]
    reasons = [explain(best, other) for other in ordered[1:]]

    warning = None
    if best["risk_miles"]["no_travel"] > 0:
        warning = "Every route crosses No Travel conditions. Consider a different departure time."
    elif best["max_level"] >= Risk.SEVERE:
        warning = "The best available route still has Severe conditions."

    return ordered, {"route_id": best["id"], "reasons": reasons, "warning": warning}
