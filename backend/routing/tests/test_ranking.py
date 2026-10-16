from routing.ranking import rank


def route(name, severe=0, high=0, no_travel=0, avg=0.0, hours=10, max_level=0):
    return {
        "id": name.lower(),
        "name": f"Route {name}",
        "risk_miles": {"low": 0, "moderate": 0, "high": high, "severe": severe, "no_travel": no_travel},
        "avg_risk": avg,
        "trip_s": hours * 3600,
        "max_level": max_level,
    }


def ids(routes):
    return [r["id"] for r in routes]


def test_fewest_severe_miles_beats_everything_below_it():
    ordered, rec = rank([
        route("A", severe=10, high=0, avg=0.1, hours=8),
        route("B", severe=0, high=200, avg=1.5, hours=14),
    ])
    assert ids(ordered) == ["b", "a"]
    assert "Severe miles" in rec["reasons"][0]


def test_high_miles_break_severe_tie():
    ordered, _ = rank([route("A", high=50), route("B", high=20)])
    assert ids(ordered) == ["b", "a"]


def test_average_risk_then_time():
    ordered, _ = rank([
        route("A", avg=0.8, hours=9),
        route("B", avg=0.3, hours=11),
        route("C", avg=0.3, hours=10),
    ])
    assert ids(ordered) == ["c", "b", "a"]


def test_tiny_risk_difference_does_not_override_travel_time():
    # 0.01 apart rounds to the same bucket, so the faster route wins
    ordered, rec = rank([route("A", avg=0.21, hours=12), route("B", avg=0.22, hours=9)])
    assert ids(ordered) == ["b", "a"]
    assert "travel time" in rec["reasons"][0]


def test_no_travel_ranks_last_and_warns():
    ordered, rec = rank([route("A", no_travel=5, hours=5), route("B", severe=40, hours=9, max_level=3)])
    assert ids(ordered) == ["b", "a"]
    assert rec["warning"]
    assert ordered[0]["recommended"] and not ordered[1]["recommended"]
