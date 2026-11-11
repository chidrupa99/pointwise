"""Signing in with PayPal.

"Log In with PayPal" is PayPal's OpenID Connect flow: send the user to PayPal,
get an authorization code back on a registered return URL, swap it for a token,
read the profile. On a PayPal hackathon it is also the right front door --
the app's whole premise is that PayPal is the payment rail.

It has one hard dependency the rest of this codebase does not: a return URL
registered on the REST app in PayPal's dashboard. We cannot set that from here,
and without it PayPal rejects the authorize request outright. So availability is
reported honestly and the app keeps a local sign-in to fall back on -- a live
third-party redirect in front of the entire product is the one place a demo
cannot afford to fail, and "nobody can open the app" is a worse failure than
"the account name is typed in rather than fetched".

The local path is NOT authentication. It stores a display name so the app has
somebody to greet and the empty state has an owner. Nothing is verified, no
password exists, and no data is protected by it. Anything that actually needs
an identity -- which is nothing here today -- must use the PayPal path.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict

from .paypal import PayPalConfig

PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "profile.json"

#: openid gets the token, profile and email get a name to show. Nothing more is
#: requested: the app has no use for an address or a phone number, and asking
#: for scopes you do not need is how a consent screen starts looking alarming.
LOGIN_SCOPES = "openid profile email"

SIGNIN_SANDBOX = "https://www.sandbox.paypal.com/signin/authorize"
SIGNIN_LIVE = "https://www.paypal.com/signin/authorize"


class AuthNotAvailable(RuntimeError):
    """Raised when the PayPal login flow cannot be started."""


class Profile(BaseModel):
    """Who the app thinks is using it."""

    model_config = ConfigDict(frozen=True)

    name: str
    email: str | None = None
    #: "paypal" when PayPal vouched for this identity, "local" when the user
    #: simply typed it. The UI says which, because the difference is real.
    method: str = "local"
    paypal_user_id: str | None = None
    signed_in_at: str = ""

    @property
    def verified(self) -> bool:
        return self.method == "paypal"


def login_redirect_uri() -> str | None:
    """The return URL registered with PayPal, if one was configured."""
    return os.environ.get("PAYPAL_LOGIN_REDIRECT_URI") or None


def login_available(config: PayPalConfig | None = None) -> tuple[bool, str | None]:
    """Whether 'Log In with PayPal' can be attempted, and why not if it cannot.

    Returns the reason as prose for the UI rather than a code, because the user
    reading it is the person who has to go and fix it in the dashboard.
    """
    cfg = config or PayPalConfig.from_env()
    if not cfg.client_id:
        return False, "PAYPAL_CLIENT_ID is not set, so there is no app to log in to."
    if not login_redirect_uri():
        return False, (
            "No return URL is registered. Add PAYPAL_LOGIN_REDIRECT_URI to .env and "
            "register the same URL under Log In with PayPal on the REST app in "
            "PayPal's dashboard."
        )
    return True, None


def authorize_url(state: str, config: PayPalConfig | None = None) -> str:
    """Where to send the browser to start the flow."""
    cfg = config or PayPalConfig.from_env()
    ok, reason = login_available(cfg)
    if not ok:
        raise AuthNotAvailable(reason or "PayPal login is not configured.")
    base = SIGNIN_LIVE if cfg.environment == "live" else SIGNIN_SANDBOX
    return f"{base}?" + urlencode(
        {
            "client_id": cfg.client_id,
            "response_type": "code",
            "scope": LOGIN_SCOPES,
            "redirect_uri": login_redirect_uri(),
            # Carried through the redirect and checked on the way back, so a
            # code delivered by anyone other than the flow we started is
            # refused rather than exchanged.
            "state": state,
        }
    )


def new_state() -> str:
    return secrets.token_urlsafe(24)


def exchange_code(code: str, config: PayPalConfig | None = None) -> dict:
    """Swap an authorization code for tokens."""
    cfg = config or PayPalConfig.from_env()
    if not (cfg.client_id and cfg.client_secret):
        raise AuthNotAvailable("PayPal credentials are not configured.")
    response = httpx.post(
        f"{cfg.base_url}/v1/oauth2/token",
        auth=(cfg.client_id, cfg.client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": login_redirect_uri(),
        },
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_profile(access_token: str, config: PayPalConfig | None = None) -> Profile:
    """Read the signed-in user's profile from PayPal."""
    cfg = config or PayPalConfig.from_env()
    response = httpx.get(
        f"{cfg.base_url}/v1/identity/oauth2/userinfo",
        params={"schema": "paypalv1.1"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    emails = body.get("emails") or []
    primary = next(
        (e.get("value") for e in emails if e.get("primary")),
        emails[0].get("value") if emails else None,
    )
    return Profile(
        name=body.get("name") or primary or "PayPal user",
        email=primary,
        method="paypal",
        paypal_user_id=body.get("user_id") or body.get("payer_id"),
        signed_in_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def read(path: Path | str | None = None) -> Profile | None:
    """The stored profile, or None when nobody is signed in."""
    target = Path(path or PROFILE_PATH)
    if not target.exists():
        return None
    try:
        return Profile.model_validate(json.loads(target.read_text()))
    except (json.JSONDecodeError, ValueError):
        return None


def write(profile: Profile, path: Path | str | None = None) -> Profile:
    """Store the profile atomically."""
    target = Path(path or PROFILE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(profile.model_dump_json(indent=2))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return profile


def sign_out(path: Path | str | None = None) -> None:
    """Forget the profile.

    The wallet is deliberately left alone. Signing out of a demo and losing the
    cards you entered would be a hostile surprise, and nothing here is secret.
    """
    Path(path or PROFILE_PATH).unlink(missing_ok=True)
