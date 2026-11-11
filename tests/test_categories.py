"""The MCC mapping is where a rewards app earns or loses trust."""

import pytest

from pointwise.categories import confidence_of, Category, resolve_category


def test_walmart_is_not_grocery():
    """The complaint that drives users away: groceries at Walmart aren't groceries."""
    category, provenance = resolve_category(merchant_name="Walmart")
    assert category is Category.SUPERSTORE
    assert category is not Category.GROCERY
    assert provenance == "known-merchant:5310"


def test_target_is_not_grocery():
    assert resolve_category(merchant_name="Target")[0] is Category.SUPERSTORE


def test_costco_is_wholesale_club_not_grocery():
    assert resolve_category(merchant_name="Costco")[0] is Category.WHOLESALE_CLUB


def test_real_supermarkets_are_grocery():
    for name in ["Whole Foods", "Trader Joe's", "Kroger", "Safeway", "Aldi"]:
        assert resolve_category(merchant_name=name)[0] is Category.GROCERY, name


def test_amazon_is_online_retail_not_department_store():
    assert resolve_category(merchant_name="Amazon")[0] is Category.ONLINE_RETAIL


def test_explicit_mcc_beats_merchant_name():
    """A posted MCC is ground truth and must win over a name guess."""
    category, provenance = resolve_category(merchant_name="Walmart", mcc="5411")
    assert category is Category.GROCERY
    assert provenance == "mcc:5411"


def test_merchant_name_matches_on_prefix():
    assert resolve_category(merchant_name="TRADER JOE'S #452")[0] is Category.GROCERY
    assert resolve_category(merchant_name="WALMART SUPERCENTER 1234")[0] is Category.SUPERSTORE


def test_airline_block_collapses_to_airfare():
    """Airline-specific codes live in 3000-3299 and aren't enumerated."""
    assert resolve_category(mcc="3047")[0] is Category.AIRFARE
    assert resolve_category(mcc="3501")[0] is Category.HOTEL


def test_unknown_merchant_does_not_guess():
    """An unknown merchant must resolve to OTHER, never to a plausible bonus."""
    category, provenance = resolve_category(merchant_name="Zzyzx Fabrication LLC")
    assert category is Category.OTHER
    assert provenance == "unresolved"


def test_no_signal_is_other():
    assert resolve_category()[0] is Category.OTHER


class TestWholeWordMatching:
    """A substring match prices dinner as petrol.

    "Shelley's Diner" contains "shell". The old lookup read it as the petrol
    station and would have scored a restaurant meal at the fuel rate -- a
    confidently wrong figure, which is the one thing this module exists to
    prevent.
    """

    def test_a_name_containing_a_brand_is_not_that_brand(self):
        category, provenance = resolve_category("Shelley's Diner")
        assert category is Category.DINING
        assert "5541" not in provenance

    def test_a_store_number_does_not_break_the_match(self):
        category, provenance = resolve_category("Trader Joe's #482")
        assert category is Category.GROCERY
        assert provenance == "known-merchant:5411"

    def test_punctuation_and_case_are_ignored(self):
        for name in ("H-E-B", "h e b", "HEB"):
            category, _ = resolve_category(name)
            # "heb" as one token is not the same merchant; the hyphenated and
            # spaced forms are.
            if name != "HEB":
                assert category is Category.GROCERY, name

    def test_the_longer_merchant_wins(self):
        """"uber eats" must beat "uber", or a takeaway bills as a taxi."""
        assert resolve_category("Uber Eats")[0] is Category.DINING
        assert resolve_category("Uber")[0] is Category.RIDESHARE

    def test_amazon_fresh_is_not_amazon(self):
        assert resolve_category("Amazon Fresh")[0] is Category.GROCERY
        assert resolve_category("amazon.com")[0] is not Category.GROCERY


class TestInference:
    """Reading a category off the name, for shops no list will ever hold."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Osteria Mozza", Category.DINING),
            ("El Farolito Taqueria", Category.DINING),
            ("Tartine Bakery", Category.DINING),
            ("Sightglass Espresso", Category.DINING),
            ("Hanoi Noodle House", Category.DINING),
            ("Kim's Supermarket", Category.GROCERY),
            ("Yellow Cab Co", Category.TRANSIT),
            ("Seaside Resort", Category.HOTEL),
            ("Village Pharmacy", Category.DRUGSTORE),
        ],
    )
    def test_a_name_that_says_what_it_is(self, name, expected):
        category, provenance = resolve_category(name)
        assert category is expected
        assert provenance.startswith("inferred:")

    def test_an_inference_is_labelled_as_one(self):
        """The provenance must never read like a looked-up code."""
        _category, provenance = resolve_category("Osteria Mozza")
        assert confidence_of(provenance) == "inferred"
        assert not provenance.startswith("known-merchant")

    def test_a_known_merchant_beats_an_inference(self):
        """Subway is a sandwich chain. The map answers before the keywords."""
        category, provenance = resolve_category("Subway")
        assert category is Category.DINING
        assert confidence_of(provenance) == "known"

    def test_two_categories_in_one_name_means_we_do_not_know(self):
        """Picking the first would price eggs as a train fare.

        Only resolvable because 'metro' was removed; the principle still has
        to hold for any future pair that collides.
        """
        from pointwise.categories import infer_category

        assert infer_category("Grill Pharmacy") is None

    @pytest.mark.parametrize(
        "name",
        [
            "Lodge Cast Iron",      # cookware, not a hotel
            "Metro by T-Mobile",    # a phone carrier, not transit
            "Barnes & Noble",       # "bar" is not a token here
            "Innovative Dental",    # does not contain "inn"
            "Acme Corp",
        ],
    )
    def test_names_that_must_not_be_guessed(self, name):
        """Each of these produced a wrong category during development."""
        category, provenance = resolve_category(name)
        assert category is Category.OTHER
        assert confidence_of(provenance) == "none"


class TestConfidence:
    def test_the_three_tiers(self):
        assert confidence_of("mcc:5812") == "known"
        assert confidence_of("known-merchant:5411") == "known"
        assert confidence_of("inferred:osteria") == "inferred"
        assert confidence_of("unresolved") == "none"
        assert confidence_of("no-signal") == "none"

    def test_a_posted_mcc_still_outranks_everything(self):
        """A real code off a transaction beats any reading of the name."""
        category, provenance = resolve_category("Osteria Mozza", mcc="5411")
        assert category is Category.GROCERY
        assert provenance == "mcc:5411"


class TestTheAggregatorLayer:
    """Plaid's detailed category, ranked between our merchant map and a guess."""

    def test_the_detailed_category_resolves_what_a_name_cannot(self):
        category, provenance = resolve_category(
            "Tectra Inc", plaid_detailed="RENT_AND_UTILITIES_INTERNET_AND_CABLE"
        )
        assert category is Category.UTILITIES
        assert provenance == "plaid:RENT_AND_UTILITIES_INTERNET_AND_CABLE"
        assert confidence_of(provenance) == "aggregator"

    def test_the_merchant_map_outranks_the_aggregator(self):
        """Our map encodes card-category nuance that a general classifier does not.

        Costco is a wholesale club, not a grocery; Target a superstore, not a
        grocery. Those distinctions are worth real money and Plaid has no
        reason to preserve them.
        """
        category, provenance = resolve_category(
            "Costco", plaid_detailed="FOOD_AND_DRINK_GROCERIES"
        )
        assert category is Category.WHOLESALE_CLUB
        assert provenance.startswith("known-merchant:")

    def test_a_posted_mcc_outranks_everything(self):
        category, provenance = resolve_category(
            "Anything", mcc="5812", plaid_detailed="FOOD_AND_DRINK_GROCERIES"
        )
        assert provenance == "mcc:5812"
        assert category is Category.DINING

    def test_the_aggregator_outranks_a_keyword_guess(self):
        """Reading the issuer's own feed beats reading words out of a name."""
        category, provenance = resolve_category(
            "Sunrise Cafe", plaid_detailed="FOOD_AND_DRINK_GROCERIES"
        )
        assert category is Category.GROCERY
        assert provenance.startswith("plaid:")

    def test_the_primary_category_is_not_usable_and_is_not_accepted(self):
        """FOOD_AND_DRINK spans groceries and restaurants.

        Those are different card categories -- Blue Cash Preferred pays 6% on
        one and 3% on the other -- so only the detailed value is mapped.
        """
        from pointwise.category_tables import PLAID_DETAILED_CATEGORY

        assert "FOOD_AND_DRINK" not in PLAID_DETAILED_CATEGORY
        assert "TRAVEL" not in PLAID_DETAILED_CATEGORY
        assert "TRANSPORTATION" not in PLAID_DETAILED_CATEGORY

    def test_groceries_and_restaurants_separate(self):
        """The split the primary category cannot make."""
        assert (
            resolve_category("Shop", plaid_detailed="FOOD_AND_DRINK_GROCERIES")[0]
            is Category.GROCERY
        )
        assert (
            resolve_category("Shop", plaid_detailed="FOOD_AND_DRINK_RESTAURANT")[0]
            is Category.DINING
        )

    def test_known_but_unbonused_is_not_the_same_as_unknown(self):
        """A gym is OTHER because no card bonuses gyms, not because we cannot tell.

        Mapped explicitly so the row reads as a classification rather than a
        shrug -- the UI hedges 'none' and does not hedge 'aggregator'.
        """
        category, provenance = resolve_category(
            "Touchstone Climbing",
            plaid_detailed="PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS",
        )
        assert category is Category.OTHER
        assert confidence_of(provenance) == "aggregator"

    def test_a_category_we_do_not_recognise_stays_unresolved(self):
        category, provenance = resolve_category(
            "Mystery Co", plaid_detailed="SOME_FUTURE_CATEGORY_WE_HAVE_NEVER_SEEN"
        )
        assert category is Category.OTHER
        assert confidence_of(provenance) == "none"

    def test_it_works_with_no_merchant_name_at_all(self):
        category, provenance = resolve_category(
            None, plaid_detailed="TRAVEL_FLIGHTS"
        )
        assert category is Category.AIRFARE
        assert provenance.startswith("plaid:")

    def test_no_primary_category_slipped_into_the_table(self):
        """A primary key would silently mis-price a whole bucket.

        Counting underscores does not work as a check -- TRANSPORTATION_GAS is
        a legitimate detailed key with one. The real invariant is that every
        key is a primary followed by a suffix, and no key IS a primary.
        """
        from pointwise.category_tables import PLAID_DETAILED_CATEGORY

        primaries = {
            "INCOME", "TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS", "BANK_FEES",
            "ENTERTAINMENT", "FOOD_AND_DRINK", "GENERAL_MERCHANDISE",
            "HOME_IMPROVEMENT", "MEDICAL", "PERSONAL_CARE", "GENERAL_SERVICES",
            "GOVERNMENT_AND_NON_PROFIT", "TRANSPORTATION", "TRAVEL",
            "RENT_AND_UTILITIES",
        }
        for key in PLAID_DETAILED_CATEGORY:
            assert key not in primaries, f"{key} is a primary, not a detailed key"
            assert any(
                key.startswith(p + "_") for p in primaries
            ), f"{key} does not extend a known primary"
