"""HTTP surface over the engine.

Thin by design: a route resolves a merchant to a category, assembles card
state, and hands both to the engine. No reward arithmetic happens here.

The engine's own routes live in this module. Money (PayPal, funding sources,
the wallet, checkout) and the chat advisor are separate routers, so neither
can quietly grow into the other.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .categories import Category, confidence_of, resolve_category
from .loader import audit
from .models import Purchase
from .places import Place, resolve_place
from .recommend import recommend
from .state import BY_ID, CATALOG, PLACES, build_states, my_cards
from . import wallet
from . import routes_auth, routes_chat, routes_money, routes_plaid

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

#: wallet.json is runtime state and is not committed, so a fresh checkout or a
#: cloud deploy starts with no cards and every recommendation comes back "no
#: eligible card". Seed it once, from the committed example, if it is absent.
#: Never overwrite an existing wallet -- that is the user's own.
if not wallet.WALLET_PATH.exists() and wallet.SEED_WALLET_PATH.exists():
    wallet.WALLET_PATH.parent.mkdir(parents=True, exist_ok=True)
    wallet.WALLET_PATH.write_text(wallet.SEED_WALLET_PATH.read_text())

app = FastAPI(title="Pointwise", version="0.1.0")
app.include_router(routes_money.router)
app.include_router(routes_auth.router)
app.include_router(routes_plaid.router)
app.include_router(routes_chat.router)


class RecommendRequest(BaseModel):
    """What the client knows at the moment of asking."""

    merchant: str = ""
    amount: Decimal = Field(gt=0)
    mcc: str | None = None
    portal: str | None = None
    is_foreign: bool = False
    on: date | None = None

    #: Simulates "I have already spent this much in this category this period",
    #: applied to every capped rule covering the resolved category. This is how
    #: the cap-crossing behaviour is demonstrated without a transaction history.
    category_spend_to_date: Decimal = Decimal("0")

    #: Rotating-category rules the user has activated.
    activated_rule_ids: list[str] = Field(default_factory=list)


@app.get("/api/cards")
def list_cards() -> dict:
    """The wallet, plus what still needs human review."""
    report = audit(CATALOG)
    return {
        "cards": [
            {
                "id": c.id,
                "issuer": c.issuer,
                "name": c.name,
                "annual_fee": str(c.annual_fee),
                "point_value_cents": str(c.point_value_cents),
                "foreign_transaction_fee_percent": str(
                    c.foreign_transaction_fee_percent
                ),
                "rules": [
                    {
                        "id": r.id,
                        "label": r.label,
                        "categories": list(r.categories),
                        "rate": str(r.rate),
                        "unit": r.unit.value,
                        "cap": r.cap.label if r.cap else None,
                        "requires_activation": r.requires_activation,
                        "requires_portal": r.requires_portal,
                        "active_quarters": list(r.active_quarters or ()),
                        "verified": r.provenance.verified_by_human,
                        "notes": r.notes,
                    }
                    for r in c.rules
                ],
            }
            for c in CATALOG
        ],
        "audit": {
            "summary": report.summary(),
            "total_rules": report.total_rules,
            "verified_rules": report.verified_rules,
            "percent_verified": report.percent_verified,
        },
    }


@app.get("/api/categories")
def list_categories() -> dict:
    return {"categories": [c.value for c in Category]}


@app.post("/api/recommend")
def post_recommend(req: RecommendRequest) -> dict:
    category, provenance = resolve_category(req.merchant or None, req.mcc)

    purchase = Purchase(
        amount=req.amount,
        category=category.value,
        on=req.on or date.today(),
        merchant_name=req.merchant or None,
        mcc=req.mcc,
        is_foreign=req.is_foreign,
        booked_via_portal=req.portal,
    )

    states = build_states(
        category.value, req.category_spend_to_date, req.activated_rule_ids
    )
    rec = recommend(my_cards(), purchase, states)

    def render(ev) -> dict:
        return {
            "card_id": ev.card_id,
            "card_name": ev.card_name,
            "issuer": BY_ID[ev.card_id].issuer,
            "annual_fee": str(BY_ID[ev.card_id].annual_fee),
            "net_value_dollars": str(ev.net_value_dollars),
            "gross_value_dollars": str(ev.gross_value_dollars),
            "fees_dollars": str(ev.fees_dollars),
            "effective_rate_percent": str(ev.effective_rate_percent),
            "caveats": list(ev.caveats),
            "unverified_rules": list(ev.unverified_rules),
            "disqualified": ev.disqualified,
            "disqualified_reason": ev.disqualified_reason,
            "components": [
                {
                    "rule_label": c.rule_label,
                    "spend_applied": str(c.spend_applied),
                    "rate": str(c.rate),
                    "unit": c.unit.value,
                    "reward_quantity": str(c.reward_quantity),
                    "value_dollars": str(c.value_dollars),
                    "reason": c.reason,
                }
                for c in ev.components
            ],
        }

    return {
        "category": category.value,
        "provenance": provenance,
        "resolved": provenance not in ("unresolved", "no-signal"),
        # "known" | "inferred" | "none". A client that renders an inferred
        # category the same as a looked-up one is passing a guess off as a
        # fact, which is the failure this field exists to prevent.
        "confidence": confidence_of(provenance),
        "explain": rec.explain(),
        "advantage_dollars": str(rec.advantage_dollars),
        "ranked": [render(e) for e in rec.ranked],
        "excluded": [render(e) for e in rec.excluded],
    }


class NearbyRequest(BaseModel):
    """Where the user is, and roughly what they are about to spend."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=400, ge=50, le=5000)
    #: A typical basket for this trip. Only affects the headline figure shown
    #: per place, not which card wins.
    amount: Decimal = Field(default=Decimal("100"), gt=0)
    activated_rule_ids: list[str] = Field(default_factory=list)


def _best_for(category: str, amount: Decimal, activated: list[str]) -> dict | None:
    """The winning card for one category, trimmed to what a notification needs."""
    purchase = Purchase(amount=amount, category=category, on=date.today())
    states = build_states(category, Decimal("0"), activated)
    rec = recommend(my_cards(), purchase, states)
    if rec.best is None:
        return None
    return {
        "card_id": rec.best.card_id,
        "card_name": rec.best.card_name,
        "net_value_dollars": str(rec.best.net_value_dollars),
        "effective_rate_percent": str(rec.best.effective_rate_percent),
        "advantage_dollars": str(rec.advantage_dollars),
        "runner_up": rec.runner_up.card_name if rec.runner_up else None,
        "headline": rec.explain(),
    }


def _render_place(place: Place, amount: Decimal, activated: list[str]) -> dict:
    return {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "provenance": place.provenance,
        "distance_m": place.distance_m,
        "is_mall": place.is_mall,
        "stores": list(place.stores),
        "best": _best_for(place.category, amount, activated),
    }


@app.post("/api/nearby")
def post_nearby(req: NearbyRequest) -> dict:
    """Merchants near a coordinate, each with the card to use there.

    When the closest hit is a mall the category is close to meaningless -- GPS
    cannot tell a food court from a department store, and the two want
    different cards. So the response says so and hands back the tenant list for
    the user to choose from, rather than guessing confidently and being wrong.
    """
    places = PLACES.nearby(req.lat, req.lon, req.radius_m)
    rendered = [_render_place(p, req.amount, req.activated_rule_ids) for p in places]

    mall = next((p for p in places if p.is_mall), None)
    in_mall = None
    if mall is not None and mall.distance_m <= 250:
        stores = []
        for name, tags in PLACES.mall_stores(mall.id):
            category, provenance = resolve_place(name, tags)
            stores.append(
                {
                    "name": name,
                    "category": category.value,
                    "provenance": provenance,
                    "best": _best_for(
                        category.value, req.amount, req.activated_rule_ids
                    ),
                }
            )
        in_mall = {
            "id": mall.id,
            "name": mall.name,
            "distance_m": mall.distance_m,
            "stores": stores,
        }

    return {
        "source": PLACES.name,
        "is_demo_data": PLACES.name == "fixture",
        "in_mall": in_mall,
        "places": rendered,
    }


if WEB_DIR.is_dir():
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
