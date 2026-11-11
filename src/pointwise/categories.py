"""Spend categories and the MCC mapping that decides which bonus a purchase trips.

The merchant category code is assigned by the merchant's acquiring bank and
travels in the authorization message. The issuer reads it to decide the bonus
category -- not the store's name, and not the contents of the basket. Every
"but I bought groceries there" complaint traces back to that fact, so the
mismatches are encoded here explicitly rather than inferred.
"""

from __future__ import annotations

import re

from .enums import Category


TRAVEL_CATEGORIES: frozenset[Category] = frozenset(
    {
        Category.AIRFARE,
        Category.HOTEL,
        Category.CAR_RENTAL,
        Category.CRUISE,
        Category.TRANSIT,
        Category.RIDESHARE,
    }
)

#: MCC -> internal category. Not exhaustive; covers the codes that carry
#: consumer bonus categories. Source: ISO 18245 / publicly published network
#: lists.
__all__ = [
    "Category",
    "TRAVEL_CATEGORIES",
    "category_for_mcc",
    "confidence_of",
    "infer_category",
    "mcc_for_merchant",
    "resolve_category",
]

from .category_tables import (  # noqa: E402
    KEYWORD_CATEGORY,
    KNOWN_MERCHANT_MCC,
    MCC_TO_CATEGORY,
    PLAID_DETAILED_CATEGORY,
)


def category_for_mcc(mcc: str) -> Category:
    """Map an MCC to an internal category, falling back to OTHER.

    Airline-specific codes occupy the 3000-3299 block; they are collapsed to
    AIRFARE rather than enumerated.
    """
    if mcc in MCC_TO_CATEGORY:
        return MCC_TO_CATEGORY[mcc]
    if mcc.isdigit():
        code = int(mcc)
        if 3000 <= code <= 3299:
            return Category.AIRFARE
        if 3300 <= code <= 3499:
            return Category.CAR_RENTAL
        if 3500 <= code <= 3999:
            return Category.HOTEL
    return Category.OTHER


def _tokens(text: str) -> list[str]:
    """Words of a merchant name, lowercased and stripped of punctuation.

    Both the map keys and the incoming name go through this, so "H-E-B" and
    "h-e-b" tokenize alike and a store number on the end is simply another
    token that nothing matches.
    """
    return re.findall(r"[a-z0-9']+", text.lower())


def _contains_phrase(haystack: list[str], needle: list[str]) -> bool:
    """Whether `needle` appears as consecutive whole words inside `haystack`."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[i : i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1)
    )


#: Longest first, so "uber eats" is tested before "uber" and the delivery
#: service is not billed as a taxi.
_MERCHANTS_BY_SPECIFICITY: list[tuple[list[str], str]] = sorted(
    ((_tokens(name), mcc) for name, mcc in KNOWN_MERCHANT_MCC.items()),
    key=lambda pair: (len(pair[0]), sum(len(w) for w in pair[0])),
    reverse=True,
)


def mcc_for_merchant(name: str) -> str | None:
    """Look up the MCC a known merchant actually transacts under.

    Matches on whole words, not substrings. A substring match reads "Shelley's
    Diner" as the Shell petrol station and prices a dinner as a fuel purchase
    -- the exact failure this whole module exists to prevent, since a wrong
    category produces a confidently wrong dollar figure.

    Returns None when the merchant is unknown. The caller must not assume a
    default from that.
    """
    words = _tokens(name)
    if not words:
        return None
    for merchant_words, mcc in _MERCHANTS_BY_SPECIFICITY:
        if _contains_phrase(words, merchant_words):
            return mcc
    return None


def infer_category(name: str) -> tuple[Category, str] | None:
    """Guess a category from the words in a merchant's name.

    Returns (category, the word it was read from), or None when the name says
    nothing or says two different things. Disagreement is the interesting case:
    "Metro Diner" matches both transit and dining, and picking the first would
    price a plate of eggs as a train fare. Two categories means we do not know,
    and saying so is the correct answer.
    """
    hits: dict[Category, str] = {}
    for word in _tokens(name):
        category = KEYWORD_CATEGORY.get(word)
        if category is not None:
            hits.setdefault(category, word)
    if len(hits) != 1:
        return None
    category, word = next(iter(hits.items()))
    return category, word


def resolve_category(
    merchant_name: str | None = None,
    mcc: str | None = None,
    plaid_detailed: str | None = None,
) -> tuple[Category, str]:
    """Resolve a purchase to a category, returning (category, provenance).

    Four layers, most trustworthy first, and the provenance says which answered
    so nothing downstream has to guess how much to trust the category:

        mcc:5812             off a posted transaction -- ground truth
        known-merchant:5814  a chain we hold the real code for
        plaid:TRAVEL_FLIGHTS the aggregator's own reading of the statement
        inferred:osteria     read from the name; a guess, and labelled one
        unresolved           nothing is known, or two things conflict

    The merchant map outranks the aggregator on purpose: it encodes the
    card-category nuance deliberately, and Plaid's taxonomy does not. Costco is
    a wholesale club rather than a grocery and Target a superstore rather than
    a grocery -- distinctions worth real money that a general-purpose
    classifier has no reason to preserve.

    The layering matters more than any single layer. A guess presented as a
    fact is the one failure this product cannot survive, and a shrug is a
    perfectly good answer when the alternative is a confident wrong number.
    """
    if mcc:
        return category_for_mcc(mcc), f"mcc:{mcc}"
    if merchant_name:
        looked_up = mcc_for_merchant(merchant_name)
        if looked_up:
            return category_for_mcc(looked_up), f"known-merchant:{looked_up}"
        if plaid_detailed and plaid_detailed in PLAID_DETAILED_CATEGORY:
            return PLAID_DETAILED_CATEGORY[plaid_detailed], f"plaid:{plaid_detailed}"
        guess = infer_category(merchant_name)
        if guess is not None:
            category, word = guess
            return category, f"inferred:{word}"
        return Category.OTHER, "unresolved"
    if plaid_detailed and plaid_detailed in PLAID_DETAILED_CATEGORY:
        return PLAID_DETAILED_CATEGORY[plaid_detailed], f"plaid:{plaid_detailed}"
    return Category.OTHER, "no-signal"


def confidence_of(provenance: str) -> str:
    """How much weight a resolution deserves: "known", "inferred" or "none".

    Callers use this to decide whether to state a category or to hedge it. The
    difference is user-visible on purpose.
    """
    if provenance.startswith(("mcc:", "known-merchant:")):
        return "known"
    if provenance.startswith("plaid:"):
        # The issuer's own feed, classified by the aggregator. Not a reading of
        # a merchant's name, so the UI need not hedge it -- but recorded
        # distinctly, because it is still somebody else's classifier.
        return "aggregator"
    if provenance.startswith("inferred:"):
        return "inferred"
    return "none"
