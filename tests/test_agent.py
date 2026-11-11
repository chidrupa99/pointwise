"""The chat advisor.

Two things are worth protecting with tests here. The loop invariants -- one
user message per batch of tool results, a hard turn budget, graceful refusal --
because getting them wrong degrades quietly rather than failing. And the
boundary: the model is given no tool that can spend money or do arithmetic.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pointwise.activity import load_demo_activity
from pointwise.agent import Advisor, AgentNotConfigured, MAX_TOOL_TURNS
from pointwise.agent_text import (
    MAX_SUGGESTIONS,
    _plain,
    split_suggestions,
    usable_key,
)
from pointwise.agent_prompt import SYSTEM, TOOLS


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_block(name: str, args: dict, block_id: str = "tu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=args, id=block_id)


class FakeClient:
    """Replays scripted responses and records every request it was sent."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Snapshot the message list. The loop appends to the same list object on
        # every turn, so storing the reference would make each recorded request
        # show the *final* history rather than what that call actually sent.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        content, stop = self._responses.pop(0) if self._responses else ([], "end_turn")
        return SimpleNamespace(
            content=content,
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


@pytest.fixture
def advisor():
    return Advisor(client=FakeClient())


class TestTheBoundary:
    def test_no_tool_can_spend_money(self):
        """The model advises; a human taps Buy.

        An LLM that can move money on its own inference is a different and much
        worse product, so the absence of that tool is a tested property.
        """
        names = {t["name"] for t in TOOLS}
        for forbidden in ("checkout", "buy", "pay", "charge", "provision", "vault"):
            assert not any(forbidden in n for n in names), names

    def test_every_tool_has_a_description(self):
        for tool in TOOLS:
            assert tool["description"].strip()
            assert tool["input_schema"]["type"] == "object"

    def test_the_prompt_forbids_doing_the_arithmetic(self):
        flat = " ".join(SYSTEM.split())
        assert "you never calculate a reward" in flat
        assert "must have come back from a tool" in flat
        assert "never estimate one" in flat

    def test_the_prompt_lists_the_real_categories(self):
        """A taxonomy that drifts from the engine's would send the model guessing."""
        from pointwise.categories import Category

        for category in Category:
            assert category.value in SYSTEM


class TestToolDispatch:
    def test_the_wallet_is_readable(self, advisor):
        result, summary, ok = advisor.dispatch("list_my_cards", {})
        assert ok and result["cards"]
        assert "14" in summary
        assert all(c["card_id"] for c in result["cards"])

    def test_a_ranking_comes_back_with_its_provenance(self, advisor):
        result, _, ok = advisor.dispatch(
            "find_best_card", {"merchant": "Costco", "amount": 240}
        )
        assert ok
        assert result["category"] == "wholesale_club"
        assert result["how_category_was_resolved"].startswith("known-merchant")
        assert result["ranked"][0]["card_name"]

    def test_a_cap_changes_the_ranking(self, advisor):
        """The engine's load-bearing behaviour, reachable through the tool."""
        fresh, _, _ = advisor.dispatch(
            "find_best_card", {"merchant": "Trader Joe's", "amount": 500}
        )
        spent, _, _ = advisor.dispatch(
            "find_best_card",
            {
                "merchant": "Trader Joe's",
                "amount": 500,
                "category_spend_to_date": 5800,
            },
        )
        by_name = lambda r: {c["card_name"]: c["value_dollars"] for c in r["ranked"]}
        assert by_name(fresh) != by_name(spent)

    @pytest.mark.parametrize("amount", ["not a number", -5, 0, None])
    def test_a_bad_amount_is_rejected_not_guessed(self, advisor, amount):
        result, _, ok = advisor.dispatch(
            "find_best_card", {"merchant": "x", "amount": amount}
        )
        assert not ok and "amount" in result["error"]

    def test_an_unknown_card_lists_the_real_ones(self, advisor):
        result, _, ok = advisor.dispatch("describe_card", {"card_id": "nope"})
        assert not ok
        assert "amex-gold" in result["available_card_ids"]

    def test_an_unknown_tool_does_not_raise(self, advisor):
        result, _, ok = advisor.dispatch("rm_rf", {})
        assert not ok and "No tool named" in result["error"]

    def test_nearby_without_a_location_says_so(self, advisor):
        result, _, ok = advisor.dispatch("whats_nearby", {})
        assert not ok and "not shared" in result["error"]

    def test_nearby_with_a_location_returns_cards(self):
        """Coordinates come from the app, never from the model.

        The tool takes no arguments precisely so a hallucinated latitude is not
        expressible.
        """
        advisor = Advisor(client=FakeClient())
        advisor._location = (37.3250, -121.9450)
        result, _, ok = advisor.dispatch("whats_nearby", {})
        assert ok and result["places"]
        assert result["is_demo_data"] is True
        assert result["places"][0]["best_card"]["card_name"]

    def test_the_audit_finds_the_misses(self, advisor):
        result, _, ok = advisor.dispatch("review_my_spending", {"limit": 3})
        assert ok
        assert result["transactions_reviewed"] > 0
        assert len(result["biggest_misses"]) <= 3
        assert float(result["total_left_on_the_table_dollars"]) > 0


class TestTheLoop:
    def test_a_plain_answer_needs_no_tools(self):
        client = FakeClient(([text_block("Use the Gold.")], "end_turn"))
        reply = Advisor(client=client).answer([{"role": "user", "content": "hi"}])
        assert reply.text == "Use the Gold."
        assert reply.trace == ()
        assert reply.input_tokens == 100

    def test_a_tool_call_is_executed_and_traced(self):
        client = FakeClient(
            ([tool_block("list_my_cards", {})], "tool_use"),
            ([text_block("You hold 14 cards.")], "end_turn"),
        )
        reply = Advisor(client=client).answer(
            [{"role": "user", "content": "what cards do I have"}]
        )
        assert reply.text == "You hold 14 cards."
        assert [t.name for t in reply.trace] == ["list_my_cards"]
        assert reply.trace[0].ok
        assert reply.input_tokens == 200  # accumulated across both turns

    def test_parallel_results_go_back_in_one_message(self):
        """Splitting them trains the model out of calling tools in parallel.

        The symptom is a slow extra round trip on every later question, which
        is invisible unless something asserts the shape.
        """
        client = FakeClient(
            (
                [
                    tool_block("list_my_cards", {}, "tu_a"),
                    tool_block("review_my_spending", {}, "tu_b"),
                ],
                "tool_use",
            ),
            ([text_block("done")], "end_turn"),
        )
        Advisor(client=client).answer([{"role": "user", "content": "q"}])

        sent = client.requests[-1]["messages"]
        results = [m for m in sent if m["role"] == "user" and isinstance(m["content"], list)]
        assert len(results) == 1
        assert len(results[0]["content"]) == 2
        assert {b["tool_use_id"] for b in results[0]["content"]} == {"tu_a", "tu_b"}

    def test_a_failed_tool_is_returned_as_an_error_result(self):
        client = FakeClient(
            ([tool_block("find_best_card", {"merchant": "x", "amount": -1})], "tool_use"),
            ([text_block("I need a positive amount.")], "end_turn"),
        )
        reply = Advisor(client=client).answer([{"role": "user", "content": "q"}])
        assert reply.trace[0].ok is False

        block = client.requests[-1]["messages"][-1]["content"][0]
        assert block["is_error"] is True
        assert "amount" in json.loads(block["content"])["error"]

    def test_the_tool_budget_is_finite(self):
        """A model that loops forever must not bill the user forever."""
        client = FakeClient(
            *[([tool_block("list_my_cards", {})], "tool_use")] * (MAX_TOOL_TURNS + 3)
        )
        reply = Advisor(client=client).answer([{"role": "user", "content": "q"}])
        assert reply.truncated
        assert len(reply.trace) == MAX_TOOL_TURNS
        assert len(client.requests) == MAX_TOOL_TURNS

    def test_a_refusal_becomes_a_civil_answer(self):
        client = FakeClient(([], "refusal"))
        reply = Advisor(client=client).answer([{"role": "user", "content": "q"}])
        assert "can't answer" in reply.text
        assert not reply.truncated

    def test_the_prompt_prefix_is_cacheable(self):
        client = FakeClient(([text_block("ok")], "end_turn"))
        Advisor(client=client).answer([{"role": "user", "content": "q"}])
        request = client.requests[0]
        assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert request["tools"] is TOOLS  # identical object: a stable prefix

    def test_no_key_is_a_clear_error(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        advisor = Advisor()
        assert not advisor.configured
        with pytest.raises(AgentNotConfigured, match="ANTHROPIC_API_KEY"):
            advisor.answer([{"role": "user", "content": "q"}])


class TestKeyDetection:
    """A key that is not a key must not read as configured."""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "sk-ant-...",
            "ANTHROPIC_API_KEY=sk-ant-...",
            "sk-ant-",
            "<key>",
        ],
    )
    def test_a_placeholder_is_not_a_key(self, monkeypatch, value):
        """Copying the line out of the setup instructions is the usual slip.

        Treating it as present would make the advisor claim it is connected
        and then 401 on the first question, which is a worse failure than the
        banner saying plainly that it is not.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
        assert usable_key() is None
        assert Advisor().configured is False
        with pytest.raises(AgentNotConfigured):
            Advisor().answer([{"role": "user", "content": "hi"}])

    def test_a_real_looking_key_is_accepted(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-" + "x" * 40)
        assert usable_key() is not None
        assert Advisor().configured is True

    def test_surrounding_whitespace_is_forgiven(self, monkeypatch):
        """A key pasted with a stray newline is a real key, not a typo."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "  sk-ant-api03-" + "y" * 40 + "\n")
        assert usable_key() == "sk-ant-api03-" + "y" * 40


class TestNoMarkdownReachesTheBubble:
    """The chat bubble renders plain text, so emphasis must not survive."""

    @pytest.mark.parametrize(
        "raw,want",
        [
            ("Use your **Amex Gold**.", "Use your Amex Gold."),
            ("a *single* star pair", "a single star pair"),
            ("**lead** and **trail**", "lead and trail"),
            ("multiplication 2 * 3 is left alone", "multiplication 2 * 3 is left alone"),
            ("no emphasis at all", "no emphasis at all"),
        ],
    )
    def test_emphasis_is_stripped(self, raw, want):
        assert _plain(raw) == want

    def test_the_prompt_still_asks_for_plain_text(self):
        """Belt and braces: the rule stays in the prompt as well as the code.

        The stripper is a safety net, not a licence to stop asking -- a model
        that thinks in markdown also reaches for tables and bullet lists,
        which no regex here removes.
        """
        assert "no markdown" in " ".join(SYSTEM.split())


class TestTheAdvisorAuditsWhatTheAppShows:
    """The advisor must not contradict the screen the user is looking at."""

    def test_the_activity_source_is_consulted(self):
        """Fixtures are the fallback, not the default.

        Before this, review_my_spending always read the 18-row demo file while
        the Activity screen showed PayPal's real transactions -- so the two
        gave different answers to 'what am I leaving on the table'.
        """
        rows = load_demo_activity()[:3]
        calls = []

        def source():
            calls.append(1)
            return rows

        advisor = Advisor(activity_source=source)
        result, _summary = advisor._review_my_spending({})

        assert calls == [1], "the source was not consulted"
        assert result["transactions_reviewed"] == 3

    def test_it_is_read_per_question_not_once(self):
        """A purchase made mid-demo has to appear in the next answer."""
        rows = load_demo_activity()
        advisor = Advisor(activity_source=lambda: rows[: len(rows)])
        first, _ = advisor._review_my_spending({})
        rows.pop()
        second, _ = advisor._review_my_spending({})
        assert second["transactions_reviewed"] == first["transactions_reviewed"] - 1

    def test_an_explicit_list_still_wins(self):
        """Tests pass activity directly; that must keep working."""
        rows = load_demo_activity()[:2]
        advisor = Advisor(activity=rows, activity_source=lambda: [])
        result, _ = advisor._review_my_spending({})
        assert result["transactions_reviewed"] == 2


class TestQuickReplies:
    """The pill line the prompt asks for, and the ways it can arrive wrong."""

    def test_a_clean_line_is_parsed_and_stripped(self):
        text, opts = split_suggestions(
            "Where are you buying it?\n\n[[ Best Buy | Apple Store | Amazon ]]"
        )
        assert text == "Where are you buying it?"
        assert opts == ("Best Buy", "Apple Store", "Amazon")

    def test_an_ordinary_answer_offers_nothing(self):
        """Most replies are not questions. Pills under a finished answer would
        invite the user to re-ask something already answered."""
        text, opts = split_suggestions("Use Amex Gold. It earns $8.64 on this.")
        assert opts == ()
        assert text.endswith("$8.64 on this.")

    def test_too_many_are_capped(self):
        _text, opts = split_suggestions("Which?\n[[ A | B | C | D | E | F ]]")
        assert len(opts) == MAX_SUGGESTIONS

    def test_an_other_option_is_dropped(self):
        """The app renders its own. Two would look like a bug."""
        _text, opts = split_suggestions("Which?\n[[ Best Buy | Other ]]")
        assert opts == ("Best Buy",)

    def test_an_empty_line_yields_nothing(self):
        text, opts = split_suggestions("Which one?\n[[   ]]")
        assert opts == ()
        assert text == "Which one?"

    def test_an_overlong_option_is_discarded(self):
        """A pill is a button, not a paragraph."""
        _text, opts = split_suggestions(f"Which?\n[[ Fine | {'x' * 60} ]]")
        assert opts == ("Fine",)

    def test_only_a_trailing_line_counts(self):
        """Brackets mid-sentence are prose, not a control line."""
        text, opts = split_suggestions("I read [[ this ]] as text. Use Amex Gold.")
        assert opts == ()
        assert "[[ this ]]" in text

    def test_the_prompt_documents_the_format(self):
        flat = " ".join(SYSTEM.split())
        assert "[[" in flat
        assert "Other" in flat
