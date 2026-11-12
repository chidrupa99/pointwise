"""Money: PayPal connection, funding sources, the wallet and checkout."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .activity import score_all, wallet_summary
from .categories import confidence_of, resolve_category
from .models import Card, Purchase
from .recommend import recommend
from .state import BY_ID, CATALOG, PAYPAL, activity_feed, build_states, my_cards
from . import funding, ledger, plaid_store, wallet
from .paypal import PayPalNotConfigured

router = APIRouter()

@router.get("/api/paypal/status")
def paypal_status() -> dict:
    """What PayPal will let this app do, for the connection banner.

    Capabilities are read from the token response rather than guessed, so the
    UI can say "vault not enabled" up front instead of letting the user
    discover it as a 403 halfway through a checkout.
    """
    registry = funding.read()
    vault_v3 = vault_v1 = False
    if PAYPAL.configured:
        try:
            vault_v3 = PAYPAL.vault_v3_enabled
            vault_v1 = PAYPAL.vault_v1_enabled
        except (PayPalNotConfigured, httpx.HTTPError):
            pass  # a banner is not worth a 500

    vaulted = sum(1 for src in registry.values() if src.kind.is_vaulted)
    fundable = sum(1 for src in registry.values() if src.kind.funds_order_directly)

    if not PAYPAL.configured:
        hint = "Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to .env"
    elif not registry:
        hint = "Run scripts/vault_cards.py to give each card a funding source"
    elif not vault_v3:
        hint = (
            "Each card has a vault id, but PayPal will not let it fund a "
            "capture until 'Save payment methods' is enabled on the REST app"
        )
    else:
        hint = None

    return {
        "configured": PAYPAL.configured,
        "environment": PAYPAL.config.environment,
        "vault_v3_enabled": vault_v3,
        "vault_v1_enabled": vault_v1,
        "cards_total": len(my_cards()),
        "cards_vaulted": vaulted,
        "cards_vault_fundable": fundable,
        "hint": hint,
    }


@router.get("/api/funding")
def get_funding() -> dict:
    """The card -> funding source map, as provisioned."""
    registry = funding.read()
    sources = []
    for card in my_cards():
        src = registry.get(card.id)
        sources.append(
            {
                "card_id": card.id,
                "card_name": card.name,
                "network": src.network if src else funding.network_key(card),
                "kind": src.kind.value if src else None,
                "vault_id": src.vault_id if src else None,
                "last4": src.last4 if src else None,
                "is_vaulted": bool(src and src.kind.is_vaulted),
                "funds_order_directly": bool(src and src.kind.funds_order_directly),
                "downgrade_reason": src.downgrade_reason if src else None,
            }
        )
    return {"sources": sources, "provisioned": len(registry)}


@router.post("/api/funding/provision")
def post_provision(force: bool = False) -> dict:
    """Give every card its own funding source.

    Idempotent: a card that already has one is left alone unless `force` is
    set, so re-running never churns ids that purchases already reference.
    """
    if not PAYPAL.configured:
        raise HTTPException(
            status_code=503, detail="PayPal is not configured. Add credentials to .env."
        )

    registry = funding.read()
    provisioned, kept, failed = [], [], []
    for card in my_cards():
        if card.id in registry and not force:
            kept.append(card.id)
            continue
        try:
            registry[card.id] = funding.provision(PAYPAL, card)
        except httpx.HTTPError as exc:
            failed.append({"card_id": card.id, "error": str(exc)})
            continue
        provisioned.append(card.id)

    if provisioned:
        funding.write(registry)

    return {
        "provisioned": provisioned,
        "kept": kept,
        "failed": failed,
        "vault_fundable": sum(
            1 for src in registry.values() if src.kind.funds_order_directly
        ),
        "total": len(registry),
    }


@router.get("/api/wallet")
def get_wallet() -> dict:
    """The cards section: every card held, what it has earned, and its offer."""
    raws, source = activity_feed()
    held = wallet.read()
    mine = my_cards()
    scored = score_all(raws, mine)
    cards = wallet_summary(mine, scored)

    # Spend per card, for the welcome-offer windows. Built once here rather
    # than per card so a long feed is walked a single time.
    spend: dict[str, list[tuple[date, Decimal]]] = {}
    for row in raws:
        if row.card_id:
            spend.setdefault(row.card_id, []).append((row.on, row.amount))

    # Which cards Pointwise is actually reading a statement for. A card added
    # from the catalogue is the user telling us what they carry; it does not
    # give us their spending on it, and a tile that shows zero without saying
    # why reads as "this card earned you nothing" rather than "we cannot see
    # this card".
    reading = {
        a.card_id
        for li in plaid_store.read().links
        for a in li.accounts
        if a.card_id
    }

    # Which issuers already have a connection. Derived from the cards mapped
    # on those connections rather than by matching the institution's name,
    # because the two are not the same string -- Plaid says "Citibank Online"
    # where the corpus says "Citi", and a card would silently look
    # unconnected.
    #
    # It matters because "Connect" is the wrong word for a card whose bank is
    # already connected: the connection exists and simply did not return this
    # account.
    connected_issuers = {BY_ID[c].issuer for c in reading if c in BY_ID}

    return {
        "source": source,
        "is_demo_data": source == "fixture",
        #: The app needs this to choose between the wallet and the empty state,
        #: and must not infer it from an empty `cards` list -- that is also
        #: what a failed load looks like.
        "is_empty": held.is_empty,
        "cards": [
            {
                "card_id": w.card_id,
                "name": w.name,
                "issuer": w.issuer,
                "annual_fee": str(w.annual_fee),
                "point_value_cents": str(w.point_value_cents),
                "reward_unit": w.reward_unit.value,
                "points_earned": str(w.points_earned),
                "value_earned_dollars": str(w.value_earned_dollars),
                "missed_dollars": str(w.missed_dollars),
                "missed_points": str(w.missed_points),
                "transaction_count": w.transaction_count,
                "statement_linked": w.card_id in reading,
                "issuer_connected": w.issuer in connected_issuers,
                "opened_on": (
                    o.opened_on.isoformat()
                    if (o := held.entry(w.card_id)) and o.opened_on
                    else None
                ),
                "signup_bonus": _render_bonus(BY_ID[w.card_id], held, spend),
            }
            for w in cards
        ],
        "totals": {
            "points_earned": str(sum(w.points_earned for w in cards)),
            "value_earned_dollars": str(sum(w.value_earned_dollars for w in cards)),
            "missed_dollars": str(sum(w.missed_dollars for w in cards)),
        },
    }


def _render_bonus(
    card: Card,
    held: wallet.Wallet,
    spend: dict[str, list[tuple[date, Decimal]]],
) -> dict | None:
    """One card's welcome-offer progress, or None when there is none to show.

    None covers two different honest cases -- the card has no sourced offer,
    and the user never told us when they opened it. Neither may render as a
    bar at zero, which would read as "you have earned nothing" instead of
    "we do not know".
    """
    progress = wallet.bonus_progress(card, held.entry(card.id), spend)
    if progress is None:
        return None
    return {
        "points": str(progress.points),
        "unit": progress.unit.value,
        "worth_dollars": str(wallet.value_of(progress.points, card)),
        "spend_required": str(progress.spend_required),
        "spent": str(progress.spent),
        "remaining": str(progress.remaining),
        "percent": round(progress.percent, 1),
        "window_ends_on": progress.window_ends_on.isoformat(),
        "days_left": progress.days_left,
        "earned": progress.earned,
        "expired": progress.expired,
        "verified": card.signup_bonus is not None
        and card.signup_bonus.provenance.verified_by_human,
    }


@router.get("/api/activity")
def get_activity(card_id: str | None = None, limit: int = 100) -> dict:
    """The activity section, optionally filtered to one card."""
    raws, source = activity_feed()
    scored = score_all(raws, my_cards())
    if card_id:
        scored = [a for a in scored if a.card_id == card_id]

    # Which cards Pointwise is actually reading a statement for. A card added
    # from the catalogue is the user telling us what they carry; it does not
    # give us their spending on it, and a tile that shows zero without saying
    # why reads as "this card earned you nothing" rather than "we cannot see
    # this card".
    reading = {
        a.card_id
        for li in plaid_store.read().links
        for a in li.accounts
        if a.card_id
    }

    # Which issuers already have a connection. Derived from the cards mapped
    # on those connections rather than by matching the institution's name,
    # because the two are not the same string -- Plaid says "Citibank Online"
    # where the corpus says "Citi", and a card would silently look
    # unconnected.
    #
    # It matters because "Connect" is the wrong word for a card whose bank is
    # already connected: the connection exists and simply did not return this
    # account.
    connected_issuers = {BY_ID[c].issuer for c in reading if c in BY_ID}

    return {
        "source": source,
        "is_demo_data": source == "fixture",
        "missed_total": str(sum(a.missed_dollars for a in scored)),
        "activity": [
            {
                "transaction_id": a.transaction_id,
                "merchant_name": a.merchant_name,
                "amount": str(a.amount),
                "on": a.on.isoformat(),
                "category": a.category,
                "provenance": a.provenance,
                "category_confidence": confidence_of(a.provenance),
                "source": a.source,
                "card_id": a.card_id,
                "card_name": a.card_name,
                "earned_dollars": str(a.earned_dollars),
                "best_card_name": a.best_card_name,
                "best_dollars": str(a.best_dollars),
                "missed_dollars": str(a.missed_dollars),
                "verdict": a.verdict.value,
            }
            for a in scored[:limit]
        ],
    }


class CheckoutRequest(BaseModel):
    """Buy something, letting the engine pick the card unless told otherwise."""

    merchant: str
    amount: Decimal = Field(gt=0)
    currency: str = "USD"
    #: Pay with this card instead of the recommended one. People overrule the
    #: optimal card for real reasons -- a sign-up bonus to hit, better purchase
    #: protection, a card the merchant does not surcharge -- and the product is
    #: wrong to pretend otherwise. What it owes them is an honest record of what
    #: the choice cost, which is what the activity audit then shows.
    card_id: str | None = None
    #: Override the funding source the registry holds for the chosen card.
    #: Only needed to test a specific instrument; normally the registry wins.
    vault_id: str | None = None


@router.post("/api/checkout")
def post_checkout(req: CheckoutRequest) -> dict:
    """Execute a purchase, on the recommended card or on one the caller names.

    This is the line where advice becomes an action. The chosen card is written
    to the ledger so the audit can score it straight away, without waiting for
    PayPal's reporting to catch up -- and that scoring is honest about an
    override: a purchase put on the wrong card is recorded as a miss, with the
    gap in dollars, because a rewards app that quietly forgave its user's
    choices would have nothing to show them on the activity screen.
    """
    if not PAYPAL.configured:
        raise HTTPException(
            status_code=503,
            detail="PayPal is not configured. Add credentials to .env.",
        )

    category, provenance = resolve_category(req.merchant or None)
    purchase = Purchase(
        amount=req.amount,
        category=category.value,
        on=date.today(),
        merchant_name=req.merchant,
    )
    rec = recommend(my_cards(), purchase, build_states(category.value, Decimal("0"), []))
    if rec.best is None:
        raise HTTPException(status_code=422, detail="No eligible card for this purchase")

    if req.card_id:
        chosen = next((e for e in rec.ranked if e.card_id == req.card_id), None)
        if chosen is None:
            # Distinguish "no such card" from "that card cannot be used here":
            # the second is the engine doing its job and the caller deserves
            # to be told which it was.
            ineligible = any(e.card_id == req.card_id for e in rec.excluded)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{req.card_id} is not eligible for this purchase"
                    if ineligible
                    else f"No card with id {req.card_id!r}"
                ),
            )
    else:
        chosen = rec.best

    forgone = rec.best.net_value_dollars - chosen.net_value_dollars

    # The engine picked a card; the registry says what that card is backed by.
    # This is the join that turns a recommendation into a funded payment.
    source = funding.read().get(chosen.card_id)
    if req.vault_id:
        payment_source = {"card": {"vault_id": req.vault_id}}
        from_vault = True
    else:
        card_model = BY_ID[chosen.card_id]
        payment_source = funding.order_payment_source(card_model, source)
        from_vault = funding.funded_from_vault(source)

    try:
        order = PAYPAL.create_order(
            req.amount,
            req.currency,
            payment_source=payment_source,
            description=f"{req.merchant} via Pointwise",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"PayPal rejected the order: {exc.response.text}"
        ) from exc

    status = order.get("status", "UNKNOWN")
    captures = (
        order.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [])
    )
    capture_id = captures[0]["id"] if captures else order.get("id", "")

    ledger.append(
        ledger.LedgerEntry(
            transaction_id=capture_id,
            order_id=order.get("id", ""),
            merchant_name=req.merchant,
            amount=req.amount,
            on=date.today(),
            card_id=chosen.card_id,
            capture_status=status,
            recorded_at=datetime.now(),
            vault_id=req.vault_id or (source.vault_id if source else None),
            funding_kind=source.kind.value if source else "unknown",
            funded_from_vault=from_vault,
        )
    )

    return {
        "order_id": order.get("id"),
        "status": status,
        "capture_id": capture_id,
        "category": category.value,
        "provenance": provenance,
        "charged_card": {
            "card_id": chosen.card_id,
            "card_name": chosen.card_name,
            "net_value_dollars": str(chosen.net_value_dollars),
            "effective_rate_percent": str(chosen.effective_rate_percent),
        },
        "funding": {
            "kind": source.kind.value if source else "unknown",
            "vault_id": req.vault_id or (source.vault_id if source else None),
            "last4": source.last4 if source else None,
            # The honest bit: a card can hold a real vault id and still be
            # charged on a stand-in, so the response says which happened.
            "funded_from_vault": from_vault,
        },
        "advantage_dollars": str(rec.advantage_dollars),
        "runner_up": rec.runner_up.card_name if rec.runner_up else None,
        "explain": rec.explain(),
        # Stated even when it is zero, so a client never has to infer from the
        # absence of a field whether the advice was taken.
        "followed_recommendation": chosen.card_id == rec.best.card_id,
        "recommended_card_name": rec.best.card_name,
        "forgone_dollars": str(forgone),
    }




class AddCardRequest(BaseModel):
    """Put a card in the wallet."""

    card_id: str
    #: When the account was opened. Optional, and left out rather than guessed:
    #: without it there is no welcome-offer window, and inventing one would put
    #: a confident countdown in front of a deadline we cannot actually see.
    opened_on: date | None = None


@router.get("/api/catalog")
def get_catalog() -> dict:
    """Every card the app can price, flagged with whether it is already held.

    This is what the add-card picker browses. It is deliberately the whole
    catalog and not a search: fourteen cards fit on a phone screen, and a
    picker that makes someone type a card name correctly is a worse picker.
    """
    held = wallet.read()
    return {
        "cards": [
            {
                "card_id": c.id,
                "name": c.name,
                "issuer": c.issuer,
                "network": c.network,
                "annual_fee": str(c.annual_fee),
                "point_value_cents": str(c.point_value_cents),
                "held": held.holds(c.id),
                "headline": _headline(c),
                "signup_bonus": (
                    {
                        "points": str(c.signup_bonus.points),
                        "unit": c.signup_bonus.unit.value,
                        "spend_required": str(c.signup_bonus.spend_required),
                        "within_months": c.signup_bonus.within_months,
                        "worth_dollars": str(
                            wallet.value_of(c.signup_bonus.points, c)
                        ),
                    }
                    if c.signup_bonus
                    else None
                ),
            }
            for c in CATALOG
        ]
    }


def _headline(card: Card) -> str:
    """The card's best non-base rate, as one short phrase for the picker."""
    best = max(
        (r for r in card.rules if not r.is_catch_all),
        key=lambda r: r.rate,
        default=None,
    )
    if best is None:
        base = next((r for r in card.rules if r.is_catch_all), None)
        return f"{base.rate}x everything" if base else ""
    return best.label


@router.post("/api/wallet/cards", status_code=201)
def add_card(req: AddCardRequest) -> dict:
    """Add a card to the wallet, or correct the open date of one already in it."""
    if req.card_id not in BY_ID:
        raise HTTPException(status_code=404, detail=f"No card {req.card_id!r}")
    if req.opened_on and req.opened_on > date.today():
        raise HTTPException(
            status_code=422, detail="A card cannot have been opened in the future"
        )
    updated = wallet.add(req.card_id, req.opened_on)
    return {
        "card_id": req.card_id,
        "name": BY_ID[req.card_id].name,
        "wallet_size": len(updated.cards),
    }


@router.delete("/api/wallet/cards/{card_id}")
def remove_card(card_id: str) -> dict:
    """Drop a card from the wallet.

    The card's past activity is left alone. It happened, it was scored against
    the wallet as it stood, and rewriting history because someone closed an
    account would make the audit a worse record than their statements.
    """
    held = wallet.read()
    if not held.holds(card_id):
        raise HTTPException(status_code=404, detail=f"{card_id!r} is not in the wallet")
    updated = wallet.remove(card_id)
    return {"card_id": card_id, "wallet_size": len(updated.cards)}
