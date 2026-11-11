#!/usr/bin/env python3
"""Ask the advisor from the terminal.

Checks the whole path -- key, model, tools, engine -- without opening the
simulator. Prints which tools were consulted, because an answer whose figures
did not come from the engine is the failure worth catching.

    PYTHONPATH=src python scripts/ask.py "which card for $120 at Trader Joe's?"
    PYTHONPATH=src python scripts/ask.py          # runs a short demo script
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pointwise.agent import EFFORT, MODEL, Advisor, AgentNotConfigured  # noqa: E402

#: Each of these reaches a different tool, and the second depends on the first
#: being remembered -- which is what proves the history is actually sent.
DEMO = [
    "Which card should I use for $120 at Trader Joe's?",
    "I've already spent $5,800 on groceries this year. Does that change it?",
    "What am I leaving on the table lately?",
]


def main() -> int:
    advisor = Advisor()
    if not advisor.configured:
        print(
            "No ANTHROPIC_API_KEY found.\n\n"
            "  1. Create one at https://console.anthropic.com -> API keys\n"
            "  2. Put it in .env as ANTHROPIC_API_KEY=sk-ant-...\n"
            "  3. Re-run this script, then restart the API\n\n"
            "Do not paste the key into a chat or a commit; .env is gitignored."
        )
        return 1

    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else DEMO
    print(f"{MODEL}, effort={EFFORT}\n")

    history: list[dict] = []
    for question in questions:
        history.append({"role": "user", "content": question})
        print(f"you  {question}")
        try:
            reply = advisor.answer(history)
        except AgentNotConfigured as exc:
            print(f"     {exc}")
            return 1

        for call in reply.trace:
            print(f"     {'ok ' if call.ok else 'err'} {call.summary}")
        print(f"\n     {reply.text}\n")
        print(
            f"     [{reply.input_tokens} in / {reply.output_tokens} out"
            f"{', truncated' if reply.truncated else ''}]\n"
        )
        history.append({"role": "assistant", "content": reply.text})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
