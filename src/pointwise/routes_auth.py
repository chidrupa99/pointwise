"""Sign-in endpoints.

The OAuth callback lands in a browser, not in the app, so it answers with a
small HTML page rather than JSON. The app finds out it worked by asking
/api/auth/status again once the browser closes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import auth
from .auth import AuthNotAvailable, Profile

router = APIRouter()

#: States we have handed out and not yet seen come back. In-process and
#: deliberately simple -- this is one user on one machine, and a database for
#: a value that lives for thirty seconds would be ceremony. A restart mid-flow
#: invalidates the state, which fails closed.
_PENDING: set[str] = set()


def _profile_payload(profile: Profile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "name": profile.name,
        "email": profile.email,
        "method": profile.method,
        "verified": profile.verified,
        "signed_in_at": profile.signed_in_at,
    }


@router.get("/api/auth/status")
def auth_status() -> dict:
    """Who is signed in, and whether PayPal login can be offered."""
    available, reason = auth.login_available()
    profile = auth.read()
    return {
        "signed_in": profile is not None,
        "profile": _profile_payload(profile),
        "paypal_login_available": available,
        "paypal_login_hint": reason,
    }


@router.post("/api/auth/paypal/start")
def start_paypal_login() -> dict:
    """Begin the flow: hand the app a URL to open in a browser."""
    state = auth.new_state()
    try:
        url = auth.authorize_url(state)
    except AuthNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _PENDING.add(state)
    return {"url": url, "state": state}


@router.get("/auth/paypal/callback", response_class=HTMLResponse)
def paypal_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Where PayPal sends the browser back.

    Every failure renders as a page rather than a raw error, because whatever
    this returns is what the user is looking at.
    """
    if error:
        return _page("PayPal declined", f"PayPal returned: {error}", ok=False)
    if not code or not state:
        return _page("Missing code", "PayPal did not return an authorization code.", ok=False)
    if state not in _PENDING:
        # Either a replay, or a sign-in started before the server restarted.
        return _page(
            "That link has expired",
            "Start the sign-in again from the app.",
            ok=False,
        )
    _PENDING.discard(state)

    try:
        tokens = auth.exchange_code(code)
        profile = auth.fetch_profile(tokens["access_token"])
    except (AuthNotAvailable, httpx.HTTPError, KeyError) as exc:
        return _page("Could not finish signing in", str(exc), ok=False)

    auth.write(profile)
    return _page("Signed in", f"Welcome, {profile.name}. You can close this tab.")


class LocalSignIn(BaseModel):
    """The fallback: a name to show, nothing verified."""

    name: str = Field(min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=200)


@router.post("/api/auth/local", status_code=201)
def local_sign_in(req: LocalSignIn) -> dict:
    """Store a display name without involving PayPal.

    Exists so the app is usable when the PayPal return URL is not registered.
    It proves nothing about who is using the app and the UI must not imply
    otherwise.
    """
    profile = auth.write(
        Profile(
            name=req.name.strip(),
            email=(req.email or "").strip() or None,
            method="local",
            signed_in_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    )
    return {"profile": _profile_payload(profile)}


@router.post("/api/auth/signout")
def signout() -> dict:
    auth.sign_out()
    return {"signed_in": False}


def _page(title: str, body: str, ok: bool = True) -> HTMLResponse:
    """A plain page for the browser tab the OAuth redirect lands in."""
    accent = "#0f6b57" if ok else "#8a1c2b"
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font:16px/1.5 -apple-system,system-ui,sans-serif;margin:0;
  display:grid;place-items:center;min-height:100vh;background:#f6f7f9;color:#14192b">
  <main style="max-width:30rem;padding:2rem;text-align:center">
    <h1 style="font-size:1.4rem;margin:0 0 .5rem;color:{accent}">{title}</h1>
    <p style="margin:0;color:#4e576e">{body}</p>
  </main>
</body></html>""",
        status_code=200 if ok else 400,
    )
