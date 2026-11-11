"""The category vocabulary.

In its own module so the lookup tables and the resolution logic can both import
it without importing each other.
"""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """Internal spend categories. Deliberately coarser than the MCC list."""

    DINING = "dining"
    GROCERY = "grocery"
    SUPERSTORE = "superstore"
    WHOLESALE_CLUB = "wholesale_club"
    GAS = "gas"
    EV_CHARGING = "ev_charging"
    TRANSIT = "transit"
    RIDESHARE = "rideshare"
    AIRFARE = "airfare"
    HOTEL = "hotel"
    CAR_RENTAL = "car_rental"
    CRUISE = "cruise"
    DRUGSTORE = "drugstore"
    STREAMING = "streaming"
    ENTERTAINMENT = "entertainment"
    ONLINE_RETAIL = "online_retail"
    ELECTRONICS = "electronics"
    DEPARTMENT_STORE = "department_store"
    HOME_IMPROVEMENT = "home_improvement"
    UTILITIES = "utilities"
    INSURANCE = "insurance"
    RENT = "rent"
    MEDICAL = "medical"
    OTHER = "other"


#: Travel bonuses on most cards are an umbrella over several categories.
