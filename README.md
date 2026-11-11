# Pointwise

Which credit card to use, and why. A deterministic rewards engine with an
LLM extraction pipeline in front of it.

Built for the PayPal AI Hackathon (submissions close 12 Nov 2026).

## What it can and cannot see

Pointwise ranks your cards for **any** purchase — that needs nothing but the
merchant and the amount. **It cannot choose the card for you**, and the limit is
structural, not a missing feature:

- `payment_source.card.vault_id` on an order is the **merchant's** field. The
  merchant creates the order, so the merchant names the funding source. When
  you check out at a third-party shop, you pick the card in PayPal's own sheet
  and Pointwise is not party to the transaction.
- This app's OAuth token grants 29 scopes. None of them is buyer-side. There is
  no `wallet/read`, no funding-source preference, nothing that reaches another
  account's payment methods. `wallet/mandates/*` is billing agreements.
- The merchant learns which card funded a capture. The buyer's own API does
  not: Transaction Search lags ~3h and has no card field.

### `/api/checkout` is a demo harness, not a feature

It executes a real PayPal capture on a distinct vaulted instrument per card,
which proves the engine can turn a recommendation into a funded payment. It
works because **Pointwise is the merchant there**.

**There is no purchase flow in the app** — no button, no screen, nothing in the
mobile client calls this endpoint. It is driven from a terminal:

```bash
curl -s -X POST 127.0.0.1:8077/api/checkout \
  -H 'content-type: application/json' \
  -d '{"merchant":"Blue Bottle","amount":12.50}'
```

Add `"card_id"` to force a specific card and manufacture a miss. Rows it writes
are tagged `source: "pointwise"` and the activity screen labels them *"demo
purchase · added through the API"*, because a feed that implied the user made
them would be lying about what the product is.

So the honest product is an advisor: it tells you which card earns most and
shows the arithmetic, and you tap that card yourself.

Widening the audit beyond what Pointwise routed is what `plaid.py` is for. Plaid
reads the card's own statement, so every transaction arrives tagged with the
account it posted to — which makes the payment method irrelevant. Tap, Apple
Pay, PayPal at a merchant, card number in a form: it all lands on the card.

Sandbox only, read-only, and the access token never leaves the server
(`plaid_store.redacted` is the only shape that reaches the app). `/api/plaid/
sandbox-link` mints a connected test issuer with no Link UI at all, which keeps
a login form out of the middle of a demo while exercising every downstream path.

Plaid is not a PayPal competitor here and does not move money: Venmo, a PayPal
company, uses it for the same job.

## The architecture rule

**The model writes the rules; the code does the math.**

An LLM reads cardmember agreements and emits `EarnRule` structures. A human
reviews them. The engine then evaluates them deterministically. No language
model is anywhere near a dollar figure at request time — ask one to apply a
spend cap and it will be confidently wrong, and a wrong dollar figure costs
more credibility than no figure at all.

## What works today

| Module | Does |
|---|---|
| `categories.py` | Spend taxonomy, MCC map, and the merchant mismatches that matter |
| `models.py` | The rules schema — caps, rotating quarters, activation, portals, provenance |
| `engine.py` | Deterministic evaluation, including cap splitting |
| `recommend.py` | Ranking across a wallet, with the gap to second place |
| `loader.py` | Corpus loading plus a verification audit |
| `api.py` | HTTP surface — resolves the merchant, assembles state, returns the ranking |
| `places.py` | Coordinate → nearby merchants → category, brand name beating map tags |
| `paypal.py` | OAuth, Vault v3 and v1, Orders v2, Transaction Search |
| `funding.py` | `card_id` → the PayPal instrument that actually pays |
| `agent.py` | The chat advisor's tool loop and trace |
| `agent_prompt.py` | What the advisor is told and what it is allowed to do |
| `activity.py` | Replays posted transactions through the engine: earned vs. optimal |
| `ledger.py` | Purchases this app executed, recorded at capture time |
| `web/` | Browser console |
| `mobile/` | Expo app for iOS and Android |

157 tests passing.

## Try it

### Engine and API

```bash
uv venv && uv pip install -e ".[dev]"
PYTHONPATH=src python scripts/which_card.py "Trader Joe's" 120
PYTHONPATH=src python scripts/which_card.py Walmart 120
python -m pytest
```

Serve the API and the web console on port 8077:

```bash
PYTHONPATH=src .venv/bin/uvicorn pointwise.api:app --reload --port 8077
```

### The location banner

The in-person suggestion lives in a dismissible banner at the top of Home, not
a tab. It starts as an invitation and only asks iOS for a position once tapped
— a cold permission prompt on first launch is how apps get location denied for
good.

### Demoing the in-person flow

The simulator can be told where it is, which is how to exercise geofencing
without walking anywhere:

```bash
# outside a supermarket
xcrun simctl location booted set 37.3270,-121.9490
# inside the mall, where the app should stop guessing and ask
xcrun simctl location booted set 37.3258,-121.9460
```

Place data is a fixture in `data/places.demo.json`, not a live survey. An
Overpass (OpenStreetMap) provider exists and needs no key, but the public
endpoint is frequently overloaded, so the fixture is the default and the API
reports `is_demo_data` so the UI can say so. Swap in Google Places or
Foursquare through the `PlaceProvider` protocol for anything real.

### Mobile

**Requires Node 22.13 or newer.** Expo SDK 58 refuses to run on Node 20 — it
prints a warning and then fails opaquely when it tries to open the simulator.
A `.nvmrc` in `mobile/` pins the version.

```bash
cd mobile
nvm use                 # reads .nvmrc
npx expo start --ios    # or --android
```

The app needs the API running. It reaches it at `localhost:8077` on the iOS
Simulator and `10.0.2.2:8077` on the Android emulator; set
`EXPO_PUBLIC_API_BASE` to the machine's LAN address for a physical device.

If `expo start --ios` fails with `simctl openurl ... code 60` on a machine that
has never run Expo Go, that is a race: Expo Go finished installing after the
URL was opened. Run `npx expo start` and open the project again — Expo Go is
installed by then.

## The two things the engine gets right that a lookup table doesn't

**Cap splitting.** When a purchase crosses a bonus cap, the portion under the
cap earns the bonus rate and the remainder falls to the base rate. With $5,800
of Blue Cash Preferred's $6,000 grocery cap used, a $500 grocery purchase earns
6% on $200 and 1% on $300 — $15.00, not the $30.00 a naive 6% gives.

**Value, not headline rate.** 4x on a card worth 1.8c/point is 7.2%, which
beats a 6% cashback card. Ranking by rate alone gets this backwards.

## Merchant category codes

The MCC is assigned by the merchant's acquiring bank and travels in the
authorization message. The issuer reads it to decide the bonus — not the store
name, not the basket. Consequences the code encodes:

- Walmart and Target are **discount stores** (5310), not grocery.
- Costco and Sam's Club are **wholesale clubs** (5300), not grocery.
- The MCC is invisible before you pay. It is predicted, or learned afterwards
  from the posted transaction.
- An unknown merchant resolves to `OTHER`. It never guesses a plausible bonus.

## PayPal

```bash
cp .env.example .env     # then paste a sandbox client id and secret
PYTHONPATH=src python scripts/paypal_check.py
```

`paypal_check.py` reports exactly which step fails — missing file, empty value,
stray quotes, a 401 from mismatched live/sandbox credentials, or a missing
Transaction Search permission — and never prints a secret.

Getting credentials:

1. developer.paypal.com → **Apps & Credentials** → **Sandbox** → **Create App**
   (type: Merchant).
2. Copy the **Client ID** and **Secret** into `.env`. No quotes, no spaces.
3. On that app, open **Features** and tick **Transaction Search**, then save.
   It is off by default and the activity feed needs it.
4. For the chat advisor, add `ANTHROPIC_API_KEY` to `.env` (create one at
   console.anthropic.com). Check it with
   `PYTHONPATH=src python scripts/ask.py`. Without a key the rest of the app
   is unaffected and the chat sheet says so.
5. While you are there, turn on **Save payment methods** (Vault). Without it
   each card still gets a real vault id, but PayPal will not let that id fund
   a capture, so purchases fall back to a published test card. The label
   varies by account type, so rather than trusting this instruction, run
   `scripts/vault_cards.py` afterwards — it reads the granted scopes back from
   PayPal and tells you whether it took.
5. Restart the API so it picks the credentials up.

### What a purchase actually does

Give every card its own funding source first — once, after adding cards or
after enabling a capability on the REST app:

```bash
PYTHONPATH=src python scripts/vault_cards.py
```

Then buy something:

```bash
curl -X POST localhost:8077/api/checkout -H 'Content-Type: application/json' \
  -d '{"merchant":"Trader Joe'"'"'s","amount":"64.20"}'
```

The merchant resolves to a category, the engine ranks the wallet, the registry
turns the winning `card_id` into a funding source PayPal accepts, PayPal
charges it, and the chosen card is written to `data/ledger.json`. The activity
feed scores it immediately.

Three things learned wiring this up, each of which cost a round trip:

- **`PayPal-Request-Id` is mandatory** on any order carrying a `payment_source`,
  and it is PayPal's idempotency key — without it a retried order can charge
  twice. `create_order` generates one per call and accepts a caller-supplied
  key so retries stay safe.
- **Vault has two APIs with different permissions, and only one can pay.**
  The token response lists exactly what the app is allowed to do, which is
  cheaper than discovering it as a 403 mid-checkout — so `PayPalClient` reads
  the scopes and `/api/paypal/status` reports them. Vault **v3** mints a token
  that drops into `payment_source.card.vault_id`; it needs *Save payment
  methods* on the app and returns `NOT_AUTHORIZED` without it. Vault **v1** is
  authorized on apps where v3 is not, and still stores a real per-card record
  keyed to our `card_id` via `external_card_id` — but Orders v2 rejects its id,
  and legacy Payments v1 rejects the payee, so it gives identity without
  execution. `funding.py` tries v3, falls back to v1, and falls back again to
  the published test card for the card's network. Every purchase records which
  tier paid, and `funded_from_vault` is false for anything but v3: a card can
  hold a real vault id and still be charged on a stand-in, and conflating the
  two would be the easiest lie in the whole system.
- **Transaction Search lags.** A payment that completes now does not appear in
  reporting for up to ~3 hours, so an app that reads only from it shows nothing
  at the moment the user looks. Hence `ledger.py`: our own purchases are
  recorded at capture time, Transaction Search backfills everything else, and
  the feed merges the two with the ledger winning on conflicts.

Two sandbox gotchas worth knowing in advance:

- A fresh sandbox business account has **no transaction history**, so the feed
  stays on fixtures until you generate some (Testing Tools → Sandbox accounts,
  then pay yourself from the sandbox personal account).
- Transaction Search is **merchant-scoped**: it returns the transactions of the
  business account the REST app belongs to, not a consumer's personal history.
  Reading a real user's own PayPal activity needs third-party permissions,
  which is a partner-level integration rather than a hackathon one.

Without credentials the app still runs: `/api/paypal/status` reports
`configured: false`, the home screen shows a "not connected" banner, and the
activity feed falls back to `data/activity.demo.json`. Nothing silently passes
fixtures off as real spend — every response carries `is_demo_data`.

With credentials, `/api/activity` reads the last 30 days from Transaction
Search and `/api/checkout` creates and captures an order, with `funding.py`
turning the engine's choice into the funding source. `/api/funding` shows the
map and `POST /api/funding/provision` builds it.

Two things to know:

- **Transaction Search has no documented MCC field**, so the category of a
  posted transaction is still inferred from the merchant name.
- It also does not say which of your cards funded a PayPal payment. That is why
  `RawActivity.card_id` is nullable and unknown funding scores as `UNKNOWN`
  rather than as a miss.

⚠️ Vaulting other people's cards to pay third-party merchants is payment
aggregation — against PayPal's user agreement and a money-transmission problem.
Fine in sandbox for a demo; not a product.

## The advisor: the model narrates, the code computes

The ✦ icon opens a conversation, and the division of labour inside it is the
product's whole argument. Claude reads the question, picks a tool and turns the
result into a sentence. It is given no arithmetic to do: every dollar figure in
every answer came out of `engine.py`.

That constraint is enforced in three places, because a system prompt alone is a
suggestion:

- The advisor has **five tools** — rank a purchase, read the wallet, describe
  one card, audit recent spending, look up what is nearby — and **none of them
  can move money**. There is no checkout tool, and a test asserts there never
  is one. The advisor advises; a human taps Buy.
- `whats_nearby` **takes no arguments**. The app supplies the coordinates, so a
  hallucinated latitude is not expressible. Without permission already granted
  the tool returns "location was not shared" and the advisor says so instead of
  inventing a neighbourhood.
- Every answer carries a **trace** of what was consulted, shown under the reply
  in the app. "Use the Gold, $8.64 back" from a chatbot is indistinguishable
  from a guess; "Ranked 14 cards for Trader Joe's $120.00 (grocery)" underneath
  it is not.

Tool inputs are parsed strictly rather than trusted — a non-numeric or negative
amount comes back as an error the model can read and correct, not an exception
that fails the turn. The loop is capped at six tool calls, so a confused model
cannot spend the user's money on tokens.

Defaults are `claude-opus-5-5` at **low** effort. The engine already did the
reasoning that matters, so the model's remaining job is small and should be
fast — someone is waiting at a till. Both are environment variables.

Conversation history is text-only and the client owns it; tool results from
earlier turns are not replayed. That keeps the context small and the endpoint
stateless, at the cost of the advisor occasionally looking something up twice.

`POST /api/chat` takes the conversation and optional coordinates.
`GET /api/agent/status` is what the sheet reads to decide whether to show the
"not connected" banner.

## ⚠️ The seed data is unverified

Every rule in `data/cards.seed.json` ships `verified_by_human: false`. The
rates come from general knowledge of publicly advertised terms and **must be
checked against each issuer's current cardmember agreement** before any
user-facing dollar figure is shown. Issuers revise rates, caps and fees
regularly, and several of these cards were refreshed in 2025.

`loader.audit()` reports the backlog. Draining it is the job of the review
console.

## Not built yet

- The LLM extraction pipeline that produces the rules
- Streaming the advisor's reply (it arrives in one piece today)
- Live Activity / Dynamic Island hand-off (needs a dev build, not Expo Go)
- Real card state: the app simulates prior category spend with presets instead
  of reading it from an aggregator
- Point valuation tuned to redemption behaviour
- `billing_cycle` and `anniversary_year` cap periods need a statement date to resolve

## Known modelling gaps

- **Citi Custom Cash** pays 5% only on the single top eligible category per
  cycle. One purchase can't settle which that is, so the engine attaches a
  caveat rather than guessing.
- **Citi Double Cash** earns 1% at purchase and 1% at payment. Treated as 2%
  up front; a cash-flow-accurate model would split it.
- Annual fees are not yet amortised into the per-purchase answer.
