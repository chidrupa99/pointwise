"""The chat advisor's HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import agent as agent_module
from .agent import AgentNotConfigured
from .state import ADVISOR

router = APIRouter()

class ChatTurn(BaseModel):
    """One text turn. Tool blocks never cross the wire."""

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """A conversation so far, plus where the user is if they have shared it.

    History is text-only and the client owns it. Tool results from earlier
    turns are deliberately not replayed: it keeps the context small and the
    endpoint stateless, at the cost of the model occasionally looking something
    up twice.
    """

    messages: list[ChatTurn] = Field(min_length=1, max_length=40)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


@router.get("/api/agent/status")
def agent_status() -> dict:
    """Whether the advisor can answer, for the chat sheet's empty state."""
    return {
        "configured": ADVISOR.configured,
        "model": agent_module.MODEL,
        "effort": agent_module.EFFORT,
        "hint": (
            None
            if ADVISOR.configured
            else "Add ANTHROPIC_API_KEY to .env to enable the chat advisor"
        ),
    }


@router.post("/api/chat")
def post_chat(req: ChatRequest) -> dict:
    """Answer a question about the wallet.

    The model picks the tools; the engine produces every figure. The trace is
    returned so the UI can show which parts of the system were consulted --
    the user should be able to see that the number was computed, not recalled.
    """
    if req.messages[-1].role != "user":
        raise HTTPException(
            status_code=422, detail="The last message must be from the user."
        )

    location = (req.lat, req.lon) if req.lat is not None and req.lon is not None else None

    try:
        reply = ADVISOR.answer(
            [{"role": m.role, "content": m.content} for m in req.messages],
            location=location,
        )
    except AgentNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # the SDK's error surface is wide; one place to map it
        raise HTTPException(
            status_code=502, detail=f"The advisor could not answer: {exc}"
        ) from exc

    return {
        "text": reply.text,
        "suggestions": list(reply.suggestions),
        "truncated": reply.truncated,
        "trace": [
            {"name": t.name, "summary": t.summary, "ok": t.ok} for t in reply.trace
        ],
        "usage": {
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
        },
    }


