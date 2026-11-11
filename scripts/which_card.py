#!/usr/bin/env python3
"""Ask which card to use. The engine's answer, with the working shown.

    python scripts/which_card.py "Trader Joe's" 120
    python scripts/which_card.py Walmart 120
    python scripts/which_card.py "United Airlines" 1200 --portal "Chase Travel"
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from pointwise.categories import resolve_category
from pointwise.loader import audit, load_cards
from pointwise.models import Purchase
from pointwise.recommend import recommend


def main() -> int:
    ap = argparse.ArgumentParser(description="Which card should I use?")
    ap.add_argument("merchant", help="Merchant name, e.g. \"Trader Joe's\"")
    ap.add_argument("amount", type=Decimal, help="Purchase amount in dollars")
    ap.add_argument("--mcc", help="Known MCC; overrides merchant-name inference")
    ap.add_argument("--portal", help="Booking channel, e.g. 'Chase Travel', 'Apple Pay'")
    ap.add_argument("--foreign", action="store_true", help="Foreign transaction")
    ap.add_argument("--on", type=date.fromisoformat, default=date.today())
    ap.add_argument("--top", type=int, default=4, help="How many cards to show")
    args = ap.parse_args()

    cards = load_cards()
    category, provenance = resolve_category(args.merchant, args.mcc)

    purchase = Purchase(
        amount=args.amount,
        category=category.value,
        on=args.on,
        merchant_name=args.merchant,
        mcc=args.mcc,
        is_foreign=args.foreign,
        booked_via_portal=args.portal,
    )
    rec = recommend(cards, purchase)

    print(f"\n  {args.merchant} · ${args.amount:,.2f} · {args.on}")
    print(f"  category: {category.value}  (via {provenance})")
    if provenance == "unresolved":
        print("  ! merchant unknown — category fell back to 'other', so this")
        print("    answer is a floor, not a prediction.")
    print()
    print(f"  → {rec.explain()}\n")

    for i, ev in enumerate(rec.ranked[: args.top], 1):
        marker = "*" if i == 1 else " "
        print(
            f"  {marker} {ev.card_name:<24} ${ev.net_value_dollars:>7,.2f}"
            f"   {ev.effective_rate_percent:>5}% effective"
        )
        for comp in ev.components:
            unit = "%" if comp.unit.value == "cashback_percent" else "x"
            print(
                f"      ${comp.spend_applied:>9,.2f} @ {comp.rate}{unit}"
                f" = ${comp.value_dollars:,.2f}   ({comp.reason})"
            )
        for caveat in ev.caveats:
            print(f"      ! {caveat}")

    if rec.excluded:
        print("\n  excluded:")
        for ev in rec.excluded:
            print(f"    - {ev.card_name}: {ev.disqualified_reason}")

    report = audit(cards)
    print(f"\n  corpus: {report.summary()}")
    print("  These rates are unverified seed data. Do not trust the dollar")
    print("  figures until the rules have been checked against issuer terms.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
