"""The conversational advisor.

The division of labour here is the whole point of the product: **the model
narrates, the code computes**. Claude reads the question, decides which tool
answers it, and turns the result into a sentence. It never multiplies a rate by
an amount. Every dollar figure the user reads came out of `engine.py`.

That is not fastidiousness. A rewards answer is consumed by someone standing at
a till with a card in their hand, and a number that is plausibly wrong is worse
than no number -- they will act on it and never find out. So the model is given
no arithmetic to do and is told, repeatedly, not to invent any.

The loop is written out rather than delegated to the SDK's tool runner because
this endpoint has to hand the UI a trace of what was actually consulted, cap
the number of tool calls, and be testable offline against a fake client.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from .activity import RawActivity, Verdict, score_all, wallet_summary
from .agent_prompt import SYSTEM, TOOLS
from .agent_text import (
    _money,
    _text_of,
    split_suggestions,
    usable_key,
)
from .categories import confidence_of, resolve_category
from .loader import load_cards
from .models import Card, Purchase
from .places import FixturePlaceProvider, PlaceProvider
from .recommend import card_states, recommend

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL = os.environ.get("POINTWISE_AGENT_MODEL", "claude-opus-5-5")
#: Deciding which tool answers a question and reading its result back is not
#: hard reasoning -- the engine already did the hard part -- and this runs while
#: someone waits at a counter. Raise it if the answers start looking shallow.
EFFORT = os.environ.get("POINTWISE_AGENT_EFFORT", "low")
#: Enough for a lookup, a follow-up and a correction; short enough that a
#: confused model cannot spend the user's money on tokens.
MAX_TOOL_TURNS = 6
MAX_TOKENS = 4096


class AgentNotConfigured(RuntimeError):
    """Raised when the advisor is asked to answer without an API key."""


class ToolCall(BaseModel):
    """One consultation, as the UI shows it.

    The trace is a product feature, not a debug log: it is what lets a user see
    that the figure came from the engine rather than from a chatbot's memory.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    summary: str
    ok: bool = True


class AgentReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    trace: tuple[ToolCall, ...] = ()
    #: Quick replies the model offered for a question it just asked. Empty
    #: whenever it was not asking one, which is most of the time.
    suggestions: tuple[str, ...] = ()
    #: True when the tool budget ran out before the model finished.
    truncated: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class Advisor:
    """Answers questions about one wallet, using the engine for every figure."""

    def __init__(
        self,
        cards: list[Card] | None = None,
        places: PlaceProvider | None = None,
        client: Any | None = None,
        activity: list[RawActivity] | None = None,
        activity_source: Callable[[], list[RawActivity]] | None = None,
        cards_source: Callable[[], list[Card]] | None = None,
    ):
        #: Read per question for the same reason the activity feed is: a card
        #: added in the app must be in the wallet the advisor answers from,
        #: and one the user does not hold must never win a recommendation.
        self._cards_source = cards_source
        self._fixed_cards = cards
        self._places = places or FixturePlaceProvider()
        self._client = client
        self._activity = activity
        #: Called per question rather than read once, because the app's feed is
        #: live: a purchase made during the demo has to show up in the answer.
        #: The app passes the same feed the Activity screen renders -- if the
        #: advisor audited a different set of transactions it would contradict
        #: the screen the user is looking at while it talks to them.
        self._activity_source = activity_source
        self._location: tuple[float, float] | None = None

    @property
    def _cards(self) -> list[Card]:
        """The wallet as it stands right now.

        An explicit list wins -- tests pass one and must not be overridden by
        whatever is on disk. Otherwise ask the source, and fall back to the
        whole catalog only when nothing else was wired up.
        """
        if self._fixed_cards is not None:
            return self._fixed_cards
        if self._cards_source is not None:
            return self._cards_source()
        return load_cards()

    @property
    def _by_id(self) -> dict[str, Card]:
        return {c.id: c for c in self._cards}

    # ------------------------------------------------------------------ setup

    @property
    def configured(self) -> bool:
        """Whether an answer can be attempted at all."""
        if self._client is not None:
            return True
        return usable_key() is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if usable_key() is None:
            raise AgentNotConfigured(
                "Set ANTHROPIC_API_KEY in .env to enable the chat advisor."
            )
        import anthropic  # imported late so the app runs without the SDK

        self._client = anthropic.Anthropic()
        return self._client

    # ------------------------------------------------------------------ tools

    def _find_best_card(self, args: dict) -> tuple[dict, str]:
        merchant = str(args.get("merchant") or "").strip()
        amount = _money(args.get("amount"), "amount")
        spend = Decimal("0")
        if args.get("category_spend_to_date") is not None:
            spend = _money(args["category_spend_to_date"], "category_spend_to_date")

        mcc = args.get("mcc")
        category, provenance = resolve_category(merchant or None, mcc)
        purchase = Purchase(
            amount=amount,
            category=category.value,
            on=date.today(),
            merchant_name=merchant or None,
            mcc=mcc,
            is_foreign=bool(args.get("is_foreign")),
            booked_via_portal=args.get("portal"),
        )
        rec = recommend(
            self._cards, purchase, card_states(self._cards, category.value, spend)
        )
        if rec.best is None:
            return ({"error": "No eligible card for this purchase."}, "no eligible card")

        result = {
            "merchant": merchant,
            "amount_dollars": f"{amount:.2f}",
            "category": category.value,
            "how_category_was_resolved": provenance,
            "category_confidence": confidence_of(provenance),
            "ranked": [
                {
                    "card_id": e.card_id,
                    "card_name": e.card_name,
                    "value_dollars": f"{e.net_value_dollars:.2f}",
                    "effective_rate_percent": f"{e.effective_rate_percent:.2f}",
                    "why": [c.reason for c in e.components],
                    "caveats": list(e.caveats),
                    "rules_unverified": bool(e.unverified_rules),
                }
                for e in rec.ranked[:4]
            ],
            "winner_beats_runner_up_by_dollars": f"{rec.advantage_dollars:.2f}",
        }
        summary = (
            f"Ranked {len(rec.ranked)} cards for {merchant or 'that purchase'} "
            f"${amount:,.2f} ({category.value})"
        )
        return result, summary

    def _list_my_cards(self, _args: dict) -> tuple[dict, str]:
        cards = [
            {
                "card_id": c.id,
                "name": c.name,
                "issuer": c.issuer,
                "annual_fee_dollars": f"{c.annual_fee:.2f}",
                "point_value_cents": f"{c.point_value_cents}",
                "foreign_transaction_fee_percent": f"{c.foreign_transaction_fee_percent}",
                "rates": [
                    f"{r.rate}{'%' if r.unit.value == 'cashback_percent' else 'x'} "
                    f"{r.label}" + (f" (cap: {r.cap.label})" if r.cap else "")
                    for r in c.rules
                ],
                "rules_awaiting_human_review": sum(
                    1 for r in c.rules if not r.provenance.verified_by_human
                ),
            }
            for c in self._cards
        ]
        return {"cards": cards}, f"Read the wallet ({len(cards)} cards)"

    def _describe_card(self, args: dict) -> tuple[dict, str]:
        card_id = str(args.get("card_id") or "")
        card = self._by_id.get(card_id)
        if card is None:
            return (
                {
                    "error": f"No card with id {card_id!r}.",
                    "available_card_ids": list(self._by_id),
                },
                f"no such card: {card_id}",
            )
        return (
            {
                "card_id": card.id,
                "name": card.name,
                "annual_fee_dollars": f"{card.annual_fee:.2f}",
                "bonus_limited_to_top_category": card.bonus_limited_to_top_category,
                "rules": [
                    {
                        "label": r.label,
                        "categories": list(r.categories) or ["everything else"],
                        "rate": f"{r.rate}",
                        "unit": r.unit.value,
                        "cap": r.cap.label if r.cap else None,
                        "active_quarters": list(r.active_quarters or ()),
                        "requires_activation": r.requires_activation,
                        "requires_portal": r.requires_portal,
                        "verified_by_human": r.provenance.verified_by_human,
                        "notes": r.notes,
                    }
                    for r in card.rules
                ],
            },
            f"Read {card.name}'s rules",
        )

    def _review_my_spending(self, args: dict) -> tuple[dict, str]:
        raws = self._activity
        if raws is None and self._activity_source is not None:
            raws = self._activity_source()
        if raws is None:
            from .activity import load_demo_activity

            raws = load_demo_activity()
        scored = score_all(raws, self._cards)

        card_id = args.get("card_id")
        if card_id:
            scored = [a for a in scored if a.card_id == card_id]

        limit = int(args.get("limit") or 5)
        misses = sorted(
            (a for a in scored if a.verdict is Verdict.MISSED),
            key=lambda a: a.missed_dollars,
            reverse=True,
        )[: max(1, limit)]

        wallet = wallet_summary(self._cards, scored)
        result = {
            "transactions_reviewed": len(scored),
            "total_earned_dollars": f"{sum(a.earned_dollars for a in scored):.2f}",
            "total_left_on_the_table_dollars": f"{sum(a.missed_dollars for a in scored):.2f}",
            "biggest_misses": [
                {
                    "merchant": a.merchant_name,
                    "amount_dollars": f"{a.amount:.2f}",
                    "on": a.on.isoformat(),
                    "card_used": a.card_name,
                    "card_that_should_have_been_used": a.best_card_name,
                    "lost_dollars": f"{a.missed_dollars:.2f}",
                }
                for a in misses
            ],
            "per_card": [
                {
                    "card_name": w.name,
                    "transactions": w.transaction_count,
                    "points_earned": f"{w.points_earned:.0f}",
                    "value_earned_dollars": f"{w.value_earned_dollars:.2f}",
                }
                for w in wallet
                if w.transaction_count
            ],
        }
        return result, f"Audited {len(scored)} purchases"

    def _whats_nearby(self, _args: dict) -> tuple[dict, str]:
        if self._location is None:
            return (
                {
                    "error": (
                        "Location was not shared. Ask the user to tap "
                        "'Use my location' on the home screen."
                    )
                },
                "no location shared",
            )
        lat, lon = self._location
        places = self._places.nearby(lat, lon, 400)
        out = []
        for place in places[:6]:
            best = self._best_for(place.category)
            out.append(
                {
                    "name": place.name,
                    "category": place.category,
                    "distance_m": place.distance_m,
                    "is_mall": place.is_mall,
                    "stores_inside": list(place.stores),
                    "best_card": best,
                }
            )
        return (
            {"is_demo_data": self._places.name == "fixture", "places": out},
            f"Looked up {len(out)} places nearby",
        )

    def _best_for(self, category: str) -> dict | None:
        """The winning card for a category on a notional $100 basket."""
        purchase = Purchase(
            amount=Decimal("100"), category=category, on=date.today()
        )
        rec = recommend(
            self._cards, purchase, card_states(self._cards, category)
        )
        if rec.best is None:
            return None
        return {
            "card_name": rec.best.card_name,
            "value_on_100_dollars": f"{rec.best.net_value_dollars:.2f}",
            "effective_rate_percent": f"{rec.best.effective_rate_percent:.2f}",
        }

    def dispatch(self, name: str, args: dict) -> tuple[dict, str, bool]:
        """Run one tool. Returns (result, summary, ok).

        A bad tool input comes back as a result rather than an exception: the
        model can read the message and correct itself, which is cheaper than
        failing the whole turn.
        """
        handlers = {
            "find_best_card": self._find_best_card,
            "list_my_cards": self._list_my_cards,
            "describe_card": self._describe_card,
            "review_my_spending": self._review_my_spending,
            "whats_nearby": self._whats_nearby,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"No tool named {name!r}."}, f"unknown tool {name}", False
        try:
            result, summary = handler(args)
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}, f"{name} rejected: {exc}", False
        return result, summary, "error" not in result

    # ------------------------------------------------------------------- loop

    def answer(
        self,
        messages: list[dict],
        location: tuple[float, float] | None = None,
    ) -> AgentReply:
        """Run the conversation to a final text answer."""
        client = self._get_client()
        self._location = location

        history = [dict(m) for m in messages]
        trace: list[ToolCall] = []
        in_tokens = out_tokens = 0

        for _ in range(MAX_TOOL_TURNS):
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM,
                        # The prompt and tool list never change, so the whole
                        # prefix is cacheable across every turn and every user.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                output_config={"effort": EFFORT},
                tools=TOOLS,
                messages=history,
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                in_tokens += getattr(usage, "input_tokens", 0) or 0
                out_tokens += getattr(usage, "output_tokens", 0) or 0

            if response.stop_reason == "refusal":
                return AgentReply(
                    text=(
                        "I can't answer that one. Ask me about your cards or a "
                        "purchase you're about to make."
                    ),
                    trace=tuple(trace),
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                )

            history.append({"role": "assistant", "content": response.content})

            calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not calls:
                answer_text, suggestions = split_suggestions(_text_of(response.content))
                return AgentReply(
                    text=answer_text,
                    suggestions=suggestions,
                    trace=tuple(trace),
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                )

            # Every tool_result for a turn goes back in ONE user message.
            # Splitting them teaches the model to stop calling tools in
            # parallel, which costs a round trip per question thereafter.
            results = []
            for call in calls:
                result, summary, ok = self.dispatch(call.name, dict(call.input or {}))
                trace.append(ToolCall(name=call.name, summary=summary, ok=ok))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": json.dumps(result, default=str),
                        "is_error": not ok,
                    }
                )
            history.append({"role": "user", "content": results})

        return AgentReply(
            text=(
                "I got stuck looking that up. Try asking about one purchase at "
                "a time -- a merchant and an amount."
            ),
            trace=tuple(trace),
            truncated=True,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )


