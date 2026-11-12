# Pointwise — PayPal AI Hackathon submission

**Which credit card to use, and why.**

- **Repository:** https://github.com/chidrupa99/pointwise
- **Demo video:** _(YouTube link)_
- **License:** MIT
- **Built by:** Chidrupa Manogna Mamunooru

---

## The problem

The average US wallet holds four credit cards, each with a different reward
structure: rotating quarterly categories, spend caps that reset annually,
points worth anywhere from 0.6 to 2.1 cents depending on how you redeem them,
and bonus categories defined not by the store's name but by a four-digit
merchant category code assigned by its acquiring bank.

So people default to one card and leave money on the counter. The information
needed to choose correctly exists — it is just spread across cardmember
agreements nobody reads and arithmetic nobody does standing at a till.

Pointwise does that arithmetic in the half second before you tap.

---

## What it does

**Ranks your wallet for any purchase.** Give it a merchant and an amount and
it returns every card you hold, ordered by what each would actually earn, with
the gap to second place. $120 at Trader Joe's and $120 at Walmart produce
different winners, because Walmart's merchant category code is *discount
store*, not grocery.

**Tells you where you are and what to use.** A banner on the home screen asks
for your position only when you tap it, resolves nearby merchants to spend
categories, and names the card. In a mall with several stores in range it
stops guessing and asks which one you are in.

**Reads your real statements.** Connect a bank through Plaid and the app pulls
posted transactions straight off the card they landed on — which makes the
payment method irrelevant. Tap, Apple Pay, PayPal, card number typed into a
form: it all posts to the card, and the card's statement is the honest record.

**Scores what you already spent.** The activity feed replays every posted
transaction through the engine and shows earned versus optimal. Over the demo
month that is $234.21 earned against $65.64 left behind, itemised by
transaction, so the number is auditable rather than asserted.

**Answers questions in plain language.** The ✦ sheet opens a Claude-powered
advisor that can rank a purchase, read your wallet, describe a card, audit
recent spending, and look up what is nearby — and every answer carries a trace
of exactly which of those it consulted.

**Manages the wallet.** Add cards from a catalogue grouped by issuer, see at a
glance which cards your bank connection can actually read — a card your bank
does not carry is disabled in the picker rather than failing later — connect
additional banks, and disconnect any of them, which revokes the token at
Plaid rather than only forgetting it locally.

---

## How it works: the model writes the rules, the code does the math

This is the one architectural decision everything else follows from.

A language model reads cardmember agreements and emits structured `EarnRule`
records — rate, category, cap, cap period, activation requirement, redemption
value, provenance. A human reviews them. From then on **no language model is
anywhere near a dollar figure.** The engine evaluates those rules
deterministically.

The reason is narrow and practical: ask an LLM to apply a $6,000 annual
grocery cap to a $500 purchase when $5,800 is already used and it will be
confidently wrong. The correct answer is 6% on $200 and 1% on $300 — $15.00,
not the $30.00 a naive 6% gives. A wrong dollar figure costs more credibility
than no dollar figure at all.

So the division of labour is: **the model narrates, the code computes.** That
constraint is enforced in the code, not just in a prompt:

- The advisor has five tools and **none of them can move money.** There is no
  checkout tool, and a test asserts there never is one.
- The "what's nearby" tool **takes no arguments** — the app supplies the
  coordinates, so a hallucinated latitude is not expressible.
- Every dollar figure in every answer came out of the engine, and the trace
  under each reply says which call produced it.

Two things this gets right that a lookup table does not:

1. **Cap splitting.** A purchase that crosses a bonus cap earns the bonus rate
   on the portion under it and the base rate on the remainder.
2. **Value, not headline rate.** 4x on a card whose points are worth 1.8¢ is
   7.2%, which beats a 6% cashback card. Ranking by advertised rate gets this
   backwards.

### Architecture

```
Expo / React Native app  ──►  FastAPI  ──►  deterministic rules engine
   (iOS + Android)                │              (engine.py, recommend.py)
                                  │
                                  ├─►  PayPal   — OAuth2, Vault v3/v1, Orders v2,
                                  │              Transaction Search
                                  ├─►  Plaid    — Link, /transactions/sync
                                  └─►  Claude   — the advisor's tool loop
```

333 tests pass with no network access.

---

## Tools used

### Claude — `claude-opus-5-5` via the Anthropic API

Used in two distinct ways.

**At runtime, as the in-app advisor.** `agent.py` runs a tool-calling loop
against five read-only tools: `rank_purchase`, `read_wallet`, `describe_card`,
`audit_spending`, `whats_nearby`. The model chooses a tool, reads the result
and turns it into a sentence. It is given no arithmetic to perform. Tool
inputs are parsed strictly, so a malformed amount returns an error the model
can read and correct rather than an exception that kills the turn, and the
loop is capped at six tool calls. It runs at **low** effort on purpose — the
engine already did the reasoning that matters, and someone is waiting at a
till. Without an `ANTHROPIC_API_KEY` the rest of the app is unaffected and the
chat sheet says the advisor is not connected.

**Offline, to build the rules corpus.** Claude reads cardmember agreements and
emits the structured `EarnRule` records the engine evaluates. Every rule
carries `verified_by_human`, and `loader.audit()` reports how many are still
unreviewed — the seed corpus currently ships entirely unverified and says so
in the README, because an unchecked rate presented as fact is the exact
failure mode this architecture exists to prevent.

**Claude Code** was also used as the development environment for this project.

### PayPal

- **OAuth2 client credentials** — `paypal.py` authenticates against the
  sandbox REST API and reads the **granted scopes back out of the token
  response**, so the app knows what it is allowed to do before it tries. That
  is what `/api/paypal/status` reports.
- **Vault (v3 with a v1 fallback)** — `funding.py` turns the engine's chosen
  `card_id` into a funding instrument, storing a per-card record keyed by
  `external_card_id`. Vault **v3** mints a token that drops straight into
  `payment_source.card.vault_id`; it requires *Save payment methods* on the
  REST app and returns `NOT_AUTHORIZED` without it. Vault **v1** is authorized
  where v3 is not and still stores a real per-card record, but Orders v2
  rejects its id — so it gives identity without execution. Every purchase
  records which tier actually paid, and `funded_from_vault` is false for
  anything but v3.
- **Orders v2** — `/api/checkout` creates and captures a real sandbox order on
  the funding source the engine chose, which proves a recommendation can
  become a funded payment. `PayPal-Request-Id` is sent on every order carrying
  a `payment_source`; it is PayPal's idempotency key, and without it a retried
  order can charge twice. This endpoint is a harness driven from a terminal —
  **there is no purchase flow in the app.**
- **Transaction Search** — backfills the activity feed. It lags about three
  hours, so `ledger.py` records our own captures at capture time and the feed
  merges the two with the ledger winning on conflicts. Worth knowing before
  you build on it: Transaction Search is **merchant-scoped** — it returns the
  transactions of the business account the REST app belongs to, not a
  consumer's personal spending history.
- **Log in with PayPal** is implemented in `auth.py` and `routes_auth.py`
  (authorization URL, code exchange, identity fetch, verified-email handling)
  but is **not active in the recorded demo**: PayPal rejects an `http://`
  return URL, and Expo Go has no HTTPS callback to register. `/api/auth/status`
  reports `paypal_login_available: false` with the reason in prose, and the
  app falls back to a name-only local profile that is explicitly labelled
  "not verified by PayPal". Setting `PAYPAL_LOGIN_REDIRECT_URI` to a
  registered HTTPS return URL turns it on.

### Plaid

Sandbox transaction aggregation against real institutions (American Express,
Capital One). Hosted Link for the connection, `/transactions/sync` for the
history, `/item/remove` on disconnect so revoking actually revokes. The access
token never leaves the server — only a redacted shape reaches the app. Plaid
is not a PayPal competitor here and moves no money; Venmo, a PayPal company,
uses it for the same job.

### Supporting

FastAPI, Pydantic, Expo / React Native, `expo-location`, and OpenStreetMap
Overpass as an optional live place provider (a fixture is the default, because
the public endpoint is frequently overloaded — and the API reports
`is_demo_data` so the interface can say which it is).

---

## Running it

Full instructions are in the [README](README.md). The short version:

```bash
git clone https://github.com/chidrupa99/pointwise.git
cd pointwise
uv venv && uv pip install -e ".[dev]"

PYTHONPATH=src .venv/bin/python scripts/which_card.py "Trader Joe's" 120
PYTHONPATH=src .venv/bin/python scripts/which_card.py Walmart 120
.venv/bin/python -m pytest -q

PYTHONPATH=src .venv/bin/uvicorn pointwise.api:app --reload --port 8077
```

Then <http://localhost:8077> for the web console, or `cd mobile && nvm use &&
npm install && npx expo start --ios` for the phone client.

**No credentials are required** to run the engine, the API, the web console or
the mobile app. Keys unlock the live PayPal, Plaid and advisor paths; without
them every endpoint degrades to bundled demo data and reports `is_demo_data`
so nothing is passed off as real spend.

---

## What is real and what is sandbox

- The rules engine, the ranking, the cap arithmetic, the category resolution
  and the activity scoring are real and fully tested.
- PayPal and Plaid run against **sandbox** credentials. The transactions are
  sandbox transactions.
- The seed rule corpus is unverified against current cardmember agreements and
  is marked as such in the data, in the loader's audit, and in the README.
- The app **advises**; it does not pay. `payment_source.card.vault_id` is the
  merchant's field, and no buyer-side PayPal scope reaches another account's
  payment methods — so Pointwise tells you which card earns most and shows the
  arithmetic, and you tap that card yourself.
