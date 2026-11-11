"""Place resolution. Brand knowledge must beat map tags, every time."""

from pointwise.categories import Category
from pointwise.places import (
    FixturePlaceProvider,
    category_from_osm,
    haversine_m,
    resolve_place,
)


def test_brand_beats_a_wrong_map_tag():
    """A map calling Walmart a supermarket must not create a grocery bonus.

    This is the single most important assertion in the module: deferring to
    the map here is how a rewards app tells someone to use the wrong card.
    """
    category, provenance = resolve_place("Walmart", {"shop": "supermarket"})
    assert category is Category.SUPERSTORE
    assert provenance == "known-merchant:5310"


def test_brand_beats_tag_for_costco():
    category, _ = resolve_place("Costco Wholesale", {"shop": "supermarket"})
    assert category is Category.WHOLESALE_CLUB


def test_unknown_brand_falls_back_to_tag():
    category, provenance = resolve_place("Hyperion Foods", {"shop": "supermarket"})
    assert category is Category.GROCERY
    assert provenance == "osm-tag:shop=supermarket"


def test_unknown_brand_and_tag_is_unresolved():
    category, provenance = resolve_place("Zzyzx Fabrication", {"office": "company"})
    assert category is Category.OTHER
    assert provenance == "unresolved"


def test_electronics_is_not_online_retail():
    """An Apple Store is not Amazon; conflating them trips the wrong 5%."""
    category, _ = resolve_place("Apple Store", {"shop": "electronics"})
    assert category is Category.ELECTRONICS
    assert category is not Category.ONLINE_RETAIL


def test_osm_tag_table_covers_the_common_kinds():
    assert category_from_osm({"amenity": "fuel"}) is Category.GAS
    assert category_from_osm({"amenity": "restaurant"}) is Category.DINING
    assert category_from_osm({"shop": "wholesale"}) is Category.WHOLESALE_CLUB
    assert category_from_osm({"amenity": "charging_station"}) is Category.EV_CHARGING
    assert category_from_osm({"leisure": "pitch"}) is None


def test_haversine_is_sane():
    """Roughly 111 km per degree of latitude."""
    assert 110_000 < haversine_m(37.0, -122.0, 38.0, -122.0) < 112_000
    assert haversine_m(37.0, -122.0, 37.0, -122.0) == 0


class TestFixtureProvider:
    def test_finds_places_within_radius_sorted_by_distance(self):
        provider = FixturePlaceProvider()
        places = provider.nearby(37.3270, -121.9490, 400)
        assert places
        assert [p.distance_m for p in places] == sorted(p.distance_m for p in places)
        assert places[0].name == "Trader Joe's"

    def test_radius_excludes_distant_places(self):
        provider = FixturePlaceProvider()
        tight = provider.nearby(37.3270, -121.9490, 60)
        wide = provider.nearby(37.3270, -121.9490, 2000)
        assert len(tight) < len(wide)

    def test_mall_is_flagged_and_carries_tenants(self):
        provider = FixturePlaceProvider()
        places = provider.nearby(37.3258, -121.9460, 100)
        mall = next(p for p in places if p.is_mall)
        assert mall.name == "Westfield Valley Fair"
        assert "Din Tai Fung" in mall.stores

    def test_mall_tenants_resolve_to_different_categories(self):
        """The point of the pick-a-store journey: tenants disagree."""
        provider = FixturePlaceProvider()
        resolved = {
            name: resolve_place(name, tags)[0]
            for name, tags in provider.mall_stores("valley-fair")
        }
        assert resolved["Din Tai Fung"] is Category.DINING
        assert resolved["Nordstrom"] is Category.DEPARTMENT_STORE
        assert len(set(resolved.values())) > 1

    def test_far_away_coordinate_finds_nothing(self):
        assert FixturePlaceProvider().nearby(40.7128, -74.0060, 400) == []
