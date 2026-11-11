#!/usr/bin/env python3
"""Check the PayPal connection and say precisely what is wrong.

    PYTHONPATH=src python scripts/paypal_check.py

Never prints a secret. Credentials are read from .env and only their shape is
reported, so this is safe to run with someone watching.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import httpx

from pointwise.paypal import PayPalClient, PayPalConfig

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"

OK = "  ok   "
BAD = " fail  "
WARN = " warn  "


def line(mark: str, text: str) -> None:
    print(f"[{mark}] {text}")


def main() -> int:
    print("\nPayPal connection check\n" + "-" * 48)

    # --- 1. the file -------------------------------------------------
    if not ENV.exists():
        line(BAD, f"{ENV} is missing")
        print("\n      cp .env.example .env    then paste your credentials\n")
        return 1
    line(OK, ".env found")

    config = PayPalConfig.from_env()

    # --- 2. the values ------------------------------------------------
    if not config.client_id:
        line(BAD, "PAYPAL_CLIENT_ID is empty")
        return 1
    if not config.client_secret:
        line(BAD, "PAYPAL_CLIENT_SECRET is empty")
        return 1

    # Shape only. A sandbox client id is a long base64-ish string; a stray
    # quote or a trailing space is the most common paste error.
    cid = config.client_id
    line(OK, f"client id present ({len(cid)} chars, starts {cid[:6]}…)")
    if cid != cid.strip() or config.client_secret != config.client_secret.strip():
        line(WARN, "credentials have surrounding whitespace — strip it")
    if cid.startswith(("'", '"')):
        line(WARN, "client id starts with a quote — .env needs no quotes")
    line(OK, f"environment: {config.environment} ({config.base_url})")

    # --- 3. can we authenticate ---------------------------------------
    client = PayPalClient(config)
    try:
        client.access_token()
        line(OK, "OAuth token obtained — credentials are valid")
    except httpx.HTTPStatusError as exc:
        line(BAD, f"OAuth rejected: HTTP {exc.response.status_code}")
        if exc.response.status_code == 401:
            print(
                "\n      401 means the id/secret pair is wrong, or you pasted\n"
                "      LIVE credentials while PAYPAL_ENV=sandbox (or vice versa).\n"
            )
        return 1
    except httpx.HTTPError as exc:
        line(BAD, f"could not reach PayPal: {exc}")
        return 1

    # --- 4. can we read transactions ----------------------------------
    end = date.today()
    start = end - timedelta(days=7)
    try:
        found = client.list_transactions(start, end)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        line(BAD, f"Transaction Search failed: HTTP {exc.response.status_code}")
        if "NOT_AUTHORIZED" in body or exc.response.status_code == 403:
            print(
                "\n      Enable 'Transaction Search' on the REST app:\n"
                "      developer.paypal.com → Apps & Credentials → your app →\n"
                "      Features → tick Transaction Search → Save.\n"
                "      New permissions can take a few minutes to apply.\n"
            )
        return 1
    except httpx.HTTPError as exc:
        line(BAD, f"Transaction Search unreachable: {exc}")
        return 1

    line(OK, f"Transaction Search works — {len(found)} purchases in the last 7 days")

    if not found:
        line(
            WARN,
            "no transactions yet, so the app will keep showing demo activity",
        )
        print(
            "\n      A fresh sandbox business account has no history. Generate\n"
            "      some: developer.paypal.com → Testing Tools → Sandbox accounts,\n"
            "      then pay yourself from the sandbox personal account, or run a\n"
            "      checkout through /api/checkout.\n"
        )
    else:
        print("\n      Most recent:")
        for txn in found[:5]:
            print(f"        {txn.on}  {txn.merchant_name[:28]:<28} ${txn.amount}")

    print("\n" + "-" * 48)
    print("Connection is good. Restart the API to pick up the credentials.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
