import math
from bisect import bisect_left

EARTH_RADIUS_MI = 3958.8
METERS_PER_MILE = 1609.344


def haversine_mi(a, b):
    """Distance in miles between two (lon, lat) points."""
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(coords):
    out = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_mi(prev, cur))
    return out


def interpolate(cum, values, target):
    """Linear interpolation of `values` (aligned with `cum`) at distance `target`."""
    if target <= cum[0]:
        return values[0]
    if target >= cum[-1]:
        return values[-1]
    i = bisect_left(cum, target)
    span = cum[i] - cum[i - 1]
    t = 0 if span == 0 else (target - cum[i - 1]) / span
    return values[i - 1] + (values[i] - values[i - 1]) * t


def point_at(coords, cum, target):
    if target <= 0:
        return tuple(coords[0])
    if target >= cum[-1]:
        return tuple(coords[-1])
    i = bisect_left(cum, target)
    span = cum[i] - cum[i - 1]
    t = 0 if span == 0 else (target - cum[i - 1]) / span
    (x1, y1), (x2, y2) = coords[i - 1], coords[i]
    return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)


def sample_distances(total, every):
    """0, every, 2*every, ... plus the end of the route."""
    marks = []
    d = 0.0
    while d < total:
        marks.append(d)
        d += every
    # drop a final mark that would sit almost on top of the destination
    if marks and total - marks[-1] < every * 0.2 and len(marks) > 1:
        marks.pop()
    marks.append(total)
    return marks


def offset_point(origin, dest, along, side_miles):
    """
    Point `along` (0..1) of the way between origin and dest, pushed `side_miles`
    perpendicular to the straight line. Used to nudge the router onto a
    different corridor when it doesn't return enough alternatives.
    """
    lon = origin[0] + (dest[0] - origin[0]) * along
    lat = origin[1] + (dest[1] - origin[1]) * along

    # work in a local flat projection, good enough for a nudge
    kx = 69.0 * math.cos(math.radians(lat))
    ky = 69.0
    dx = (dest[0] - origin[0]) * kx
    dy = (dest[1] - origin[1]) * ky
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    return (lon + nx * side_miles / kx, lat + ny * side_miles / ky)


def overlap_ratio(a, b, tolerance_mi=3.0, samples=40):
    """Rough share of route `a` that runs within `tolerance_mi` of route `b`."""
    cum_a = cumulative_miles(a)
    if cum_a[-1] == 0:
        return 1.0
    # resample b evenly so long straight segments don't leave gaps
    cum_b = cumulative_miles(b)
    n = min(1500, max(2, int(cum_b[-1] / 1.0)))
    b_pts = [point_at(b, cum_b, cum_b[-1] * k / (n - 1)) for k in range(n)]
    hits = 0
    for k in range(samples):
        p = point_at(a, cum_a, cum_a[-1] * (k + 0.5) / samples)
        if any(haversine_mi(p, q) < tolerance_mi for q in b_pts):
            hits += 1
    return hits / samples


def min_distance_to_points(p, points):
    return min(haversine_mi(p, q) for q in points)
