"""Text and input handling for the advisor.

Split out of `agent.py` so that file stays about the conversation loop. These
are the parts with no knowledge of a wallet or a model: reading the API key,
parsing money a model handed us, and deciding what of a reply reaches the user.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any


def usable_key() -> str | None:
    """The API key, if what is in the environment could actually be one.

    A key copied out of documentation rather than out of the console is the
    common mistake, and it is worse than an empty variable: the advisor would
    report itself connected and then fail with a 401 at the moment someone
    asks it a question. An ellipsis or a trailing placeholder word is never
    part of a real key, so treat those as absent and keep the honest banner.
    """
    raw = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not raw or "..." in raw or raw.endswith(("sk-ant-", "<key>", "your-key")):
        return None
    return raw



def _money(raw: Any, field: str) -> Decimal:
    """Parse a model-supplied amount strictly.

    Tool inputs are not trusted: an LLM can emit a string where a number was
    asked for, or a negative. Money is Decimal everywhere in this codebase and
    a float would quietly lose cents, so the conversion goes through str().
    """
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{field} must be positive, got {value}")
    return value



#: Emphasis the model adds despite being told not to. The chat bubble renders
#: plain text, so `**Amex Gold**` reaches the user as literal asterisks.
_EMPHASIS = re.compile(r"\*{1,2}(?=\S)(.+?)(?<=\S)\*{1,2}", re.DOTALL)


#: The quick-reply line the prompt asks for: [[ One | Two | Three ]] at the end.
_OPTIONS = re.compile(r"\n*\[\[(?P<body>[^\]]+)\]\]\s*$")

#: More than this and they stop being quick and start being a menu.
MAX_SUGGESTIONS = 4


def split_suggestions(text: str) -> tuple[str, tuple[str, ...]]:
    """Pull the quick-reply line off the end of a reply.

    Returns the text the user should read and the options the app should
    render. A malformed or empty line is dropped rather than shown: a button
    labelled with a stray bracket is worse than no button, and the user can
    always type.
    """
    match = _OPTIONS.search(text)
    if match is None:
        return text, ()
    options = [
        part.strip()
        for part in match.group("body").split("|")
        if part.strip() and len(part.strip()) <= 40
    ]
    # Drop the "Other" the prompt forbids, in case it arrives anyway -- the app
    # adds its own, and two of them side by side would look like a bug.
    options = [o for o in options if o.lower() not in {"other", "something else"}]
    return text[: match.start()].rstrip(), tuple(options[:MAX_SUGGESTIONS])


def _plain(text: str) -> str:
    """Strip the markdown emphasis the style rule asks for and does not get.

    A prompt instruction is a tendency, not a guarantee, and this one fails
    visibly: the model reaches for bold on the card name exactly where the
    answer matters most. Enforcing it here costs nothing and means the rule
    holds even when the model is having an off day or the model changes.
    """
    return _EMPHASIS.sub(r"\1", text)


def _text_of(content: list) -> str:
    """Join the text blocks of a response, ignoring thinking and tool blocks."""
    parts = [
        b.text
        for b in content
        if getattr(b, "type", None) == "text" and getattr(b, "text", "")
    ]
    return _plain("\n\n".join(parts).strip())
