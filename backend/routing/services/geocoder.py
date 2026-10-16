"""Place search via Photon (OpenStreetMap data, no key needed)."""
import requests
from django.conf import settings
from django.core.cache import cache


class GeocodeError(Exception):
    pass


def _label(props):
    parts = [props.get("name")]
    for key in ("city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(p for p in parts if p)


def search(query, limit=5):
    query = (query or "").strip()
    if len(query) < 2:
        return []

    cache_key = f"geo:{query.lower()}:{limit}"
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    try:
        resp = requests.get(
            settings.PHOTON_URL,
            params={"q": query, "limit": limit, "lang": "en"},
            timeout=settings.HTTP_TIMEOUT,
            headers={"User-Agent": settings.USER_AGENT},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodeError(f"Geocoding failed: {exc}") from exc

    results = []
    for feature in resp.json().get("features", []):
        lon, lat = feature["geometry"]["coordinates"]
        results.append({"label": _label(feature["properties"]), "lon": lon, "lat": lat})

    cache.set(cache_key, results, 60 * 60 * 24)
    return results


def resolve(place):
    """
    Accepts {"lon", "lat", "label"} from the autocomplete or a bare string
    the user typed without picking a suggestion.
    """
    if isinstance(place, dict) and "lon" in place and "lat" in place:
        return {
            "label": place.get("label") or f"{place['lat']:.4f}, {place['lon']:.4f}",
            "lon": float(place["lon"]),
            "lat": float(place["lat"]),
        }
    text = place.get("label") if isinstance(place, dict) else place
    matches = search(text, limit=1)
    if not matches:
        raise GeocodeError(f"Couldn't find “{text}”")
    return matches[0]
