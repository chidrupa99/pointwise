#!/usr/bin/env python3
"""Give every card in the wallet its own PayPal funding source.

Run once after adding cards or after enabling a new capability on the REST
app. Writes data/funding.json, which /api/checkout reads to decide what to
charge. Re-running is safe: already-provisioned cards are skipped unless
--force is passed.

    PYTHONPATH=src python scripts/vault_cards.py
    PYTHONPATH=src python scripts/vault_cards.py --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pointwise import funding  # noqa: E402
from pointwise.loader import load_cards  # noqa: E402
from pointwise.paypal import PayPalClient, PayPalNotConfigured  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-provision cards that already have one"
    )
    parser.add_argument("--card", help="provision only this card id")
    args = parser.parse_args()

    client = PayPalClient()
    if not client.configured:
        print("PayPal is not configured. Put credentials in .env first.")
        return 1

    try:
        scopes = client.granted_scopes()
    except (PayPalNotConfigured, httpx.HTTPError) as exc:
        print(f"Could not reach PayPal: {exc}")
        return 1

    print(f"{client.config.environment}, {len(scopes)} scopes granted")
    print(f"  vault v3 (fundable):     {_tick(client.vault_v3_enabled)}")
    print(f"  vault v1 (storage only): {_tick(client.vault_v1_enabled)}")
    if not client.vault_v3_enabled:
        print(
            "\n  Vault v3 is what lets a vaulted card fund a capture. Enable it at\n"
            "  developer.paypal.com -> Apps & Credentials -> your app -> Features,\n"
            "  then turn on 'Save payment methods' (it needs the account approved\n"
            "  for Expanded Checkout). Re-run this script afterwards."
        )

    cards = load_cards()
    if args.card:
        cards = [c for c in cards if c.id == args.card]
        if not cards:
            print(f"\nNo card with id {args.card!r}")
            return 1

    registry = funding.read()
    print(f"\nProvisioning {len(cards)} card(s):\n")

    changed = 0
    for card in cards:
        existing = registry.get(card.id)
        if existing and not args.force:
            print(f"  {card.id:28s} kept     {existing.label}")
            continue
        try:
            source = funding.provision(client, card)
        except httpx.HTTPError as exc:
            print(f"  {card.id:28s} FAILED   {exc}")
            continue
        registry[card.id] = source
        changed += 1
        print(f"  {card.id:28s} {'new':8s} {source.label}")
        if source.downgrade_reason:
            print(f"  {'':28s}          {source.downgrade_reason}")

    if changed:
        funding.write(registry)
        print(f"\nWrote {funding.REGISTRY_PATH}")
    else:
        print("\nNothing to do.")

    kinds: dict[str, int] = {}
    for source in registry.values():
        kinds[source.kind.value] = kinds.get(source.kind.value, 0) + 1
    print("  " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))

    fundable = sum(1 for s in registry.values() if s.kind.funds_order_directly)
    print(f"  {fundable}/{len(registry)} fund a capture from the vault itself")
    if fundable < len(registry):
        print(
            "  The rest have a real vault id but PayPal will not let it "
            "fund an Orders v2\n  capture, so those purchases fall back "
            "to the published test card for the\n  network. Enable "
            "'Save payment methods' to close the gap."
        )

    return 0


def _tick(ok: bool) -> str:
    return "yes" if ok else "no"


if __name__ == "__main__":
    raise SystemExit(main())
