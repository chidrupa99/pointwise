"""Turning a coordinate into merchants, and merchants into spend categories.

Two layers, in this order, because the order is the whole point:

1. **Brand name.** If we know the brand, we know the code it transacts under.
   Walmart is a discount store no matter what a map calls it.
2. **Map tags.** Only when the brand is unknown do we fall back to what the
   map says the place sells, which is a guess about the MCC rather than a fact.

Providers are swappable. Overpass is free but unreliable under load, so a
fixture backs it: a demo must not depend on someone else's free service.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from .categories import Category, category_for_mcc, mcc_for_merchant

DEMO_PLACES = Path(__file__).resolve().parents[2] / "data" / "places.demo.json"

#: OpenStreetMap tag -> internal category. Tags are a weaker signal than a
#: brand name: a map records what a shop sells, while an MCC records how its
#: acquirer classified it, and those disagree often enough to matter.
OSM_TO_CATEGORY: dict[tuple[str, str], Category] = {
    ("shop", "supermarket"): Category.GROCERY,
    ("shop", "grocery"): Category.GROCERY,
    ("shop", "greengrocer"): Category.GROCERY,
    ("shop", "butcher"): Category.GROCERY,
    ("shop", "bakery"): Category.GROCERY,
    ("shop", "convenience"): Category.GROCERY,
    ("shop", "department_store"): Category.DEPARTMENT_STORE,
    ("shop", "variety_store"): Category.SUPERSTORE,
    ("shop", "wholesale"): Category.WHOLESALE_CLUB,
    ("shop", "chemist"): Category.DRUGSTORE,
    ("shop", "doityourself"): Category.HOME_IMPROVEMENT,
    ("shop", "hardware"): Category.HOME_IMPROVEMENT,
    ("shop", "trade"): Category.HOME_IMPROVEMENT,
    ("shop", "clothes"): Category.DEPARTMENT_STORE,
    ("shop", "cosmetics"): Category.DEPARTMENT_STORE,
    ("shop", "electronics"): Category.ELECTRONICS,
    ("shop", "mall"): Category.DEPARTMENT_STORE,
    ("amenity", "restaurant"): Category.DINING,
    ("amenity", "fast_food"): Category.DINING,
    ("amenity", "cafe"): Category.DINING,
    ("amenity", "bar"): Category.DINING,
    ("amenity", "pub"): Category.DINING,
    ("amenity", "food_court"): Category.DINING,
    ("amenity", "fuel"): Category.GAS,
    ("amenity", "charging_station"): Category.EV_CHARGING,
    ("amenity", "pharmacy"): Category.DRUGSTORE,
    ("amenity", "cinema"): Category.ENTERTAINMENT,
    ("amenity", "theatre"): Category.ENTERTAINMENT,
    ("tourism", "hotel"): Category.HOTEL,
    ("tourism", "motel"): Category.HOTEL,
    ("amenity", "car_rental"): Category.CAR_RENTAL,
}


class Place(BaseModel):
    """A candidate merchant near the user."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    category: str
    provenance: str
    distance_m: int
    lat: float
    lon: float
    is_mall: bool = False
    stores: tuple[str, ...] = ()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def category_from_osm(tags: dict[str, str]) -> Category | None:
    """Map OSM tags to a category, or None when nothing matches."""
    for key, value in tags.items():
        hit = OSM_TO_CATEGORY.get((key, value))
        if hit is not None:
            return hit
    return None


def resolve_place(name: str, tags: dict[str, str]) -> tuple[Category, str]:
    """Resolve a place to (category, provenance).

    A known brand always wins. Walmart tagged ``shop=supermarket`` on a map is
    still a discount store to an issuer, and deferring to the map here is
    exactly how a rewards app tells someone to use the wrong card.
    """
    known = mcc_for_merchant(name)
    if known is not None:
        return category_for_mcc(known), f"known-merchant:{known}"

    from_tags = category_from_osm(tags)
    if from_tags is not None:
        pair = next(
            (f"{k}={v}" for k, v in tags.items() if (k, v) in OSM_TO_CATEGORY), "tag"
        )
        return from_tags, f"osm-tag:{pair}"

    return Category.OTHER, "unresolved"


class PlaceProvider(Protocol):
    """Anything that can answer 'what merchants are near this point'."""

    name: str

    def nearby(self, lat: float, lon: float, radius_m: int) -> list[Place]: ...


class FixturePlaceProvider:
    """Demo data with real-shaped geometry. Never fails, never rate-limits."""

    name = "fixture"

    def __init__(self, path: Path | str | None = None) -> None:
        raw = json.loads(Path(path or DEMO_PLACES).read_text())
        self._entries = raw["places"]
        self.center = raw["center"]

    def nearby(self, lat: float, lon: float, radius_m: int) -> list[Place]:
        found: list[Place] = []
        for entry in self._entries:
            distance = haversine_m(lat, lon, entry["lat"], entry["lon"])
            if distance > radius_m:
                continue
            category, provenance = resolve_place(entry["name"], entry.get("osm", {}))
            found.append(
                Place(
                    id=entry["id"],
                    name=entry["name"],
                    category=category.value,
                    provenance=provenance,
                    distance_m=round(distance),
                    lat=entry["lat"],
                    lon=entry["lon"],
                    is_mall=entry.get("is_mall", False),
                    stores=tuple(s["name"] for s in entry.get("stores", ())),
                )
            )
        found.sort(key=lambda p: p.distance_m)
        return found

    def mall_stores(self, mall_id: str) -> list[tuple[str, dict[str, str]]]:
        """The tenant list for a mall, used by the pick-a-store journey."""
        for entry in self._entries:
            if entry["id"] == mall_id:
                return [(s["name"], s.get("osm", {})) for s in entry.get("stores", ())]
        return []


class OverpassPlaceProvider:
    """OpenStreetMap via Overpass. Free, no key, and frequently overloaded."""

    name = "overpass"

    ENDPOINT = "https://overpass-api.de/api/interpreter"
    SHOPS = "supermarket|convenience|department_store|wholesale|mall|chemist|doityourself"
    AMENITIES = "restaurant|fast_food|cafe|bar|pub|fuel|pharmacy|charging_station|cinema"

    def __init__(self, timeout_s: float = 6.0) -> None:
        self.timeout_s = timeout_s

    def nearby(self, lat: float, lon: float, radius_m: int) -> list[Place]:
        import urllib.parse
        import urllib.request

        query = (
            f"[out:json][timeout:{int(self.timeout_s)}];("
            f'nwr["shop"~"{self.SHOPS}"](around:{radius_m},{lat},{lon});'
            f'nwr["amenity"~"{self.AMENITIES}"](around:{radius_m},{lat},{lon});'
            f");out center tags 40;"
        )
        request = urllib.request.Request(
            self.ENDPOINT,
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": "pointwise/0.1 (hackathon prototype)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            payload = json.loads(response.read())

        found: list[Place] = []
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name") or tags.get("brand")
            if not name:
                continue  # an unnamed node cannot be matched to a merchant
            point = element.get("center") or element
            if "lat" not in point or "lon" not in point:
                continue
            category, provenance = resolve_place(name, tags)
            found.append(
                Place(
                    id=f"osm-{element.get('type', 'n')}-{element.get('id')}",
                    name=name,
                    category=category.value,
                    provenance=provenance,
                    distance_m=round(haversine_m(lat, lon, point["lat"], point["lon"])),
                    lat=point["lat"],
                    lon=point["lon"],
                    is_mall=tags.get("shop") == "mall",
                )
            )
        found.sort(key=lambda p: p.distance_m)
        return found


def nearby(
    lat: float,
    lon: float,
    radius_m: int = 400,
    providers: list[PlaceProvider] | None = None,
) -> tuple[list[Place], str]:
    """Find nearby merchants, returning (places, which_provider_answered).

    Providers are tried in order and the first that returns anything wins. A
    provider that errors is skipped rather than propagated: losing the place
    list should degrade the suggestion, not break the app.
    """
    chain: list[PlaceProvider] = providers or [FixturePlaceProvider()]
    for provider in chain:
        try:
            found = provider.nearby(lat, lon, radius_m)
        except Exception:
            continue
        if found:
            return found, provider.name
    return [], "none"
