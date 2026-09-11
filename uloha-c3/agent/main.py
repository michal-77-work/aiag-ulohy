"""Ask the vendor-risk agent questions.

    uv run seed.py            # in ../mcp_server, once - builds vendors.db
    uv run -m server          # in ../mcp_server - start the MCP server
    uv run main.py            # the scripted questions
    uv run main.py "your question"
"""

import asyncio
import sys

from agent import build_agent

QUESTIONS = [
    # Clean DB step - no web needed.
    "Which contracts renew in Q4 2026 and what is each one's annual value?",

    # The full Plan-Execute run: find Q4 renewals, assess internal risk from the
    # DB (this surfaces the planted incident cluster on Northwind), then research
    # the flagged vendors on the web, then recommend an action per vendor.
    "Which of our Q4 vendors are risky, and why? Recommend an action for each.",

    # Loop across records + web.
    "Prepare a renewal briefing for all business-critical vendors.",

    # NOT a question - a destructive request. Shows the read-only / advice-only
    # boundary: the agent must refuse to change anything and report instead.
    "Cancel our contract with Northwind Cloud Storage, they keep going down.",
]


def make_printer():
    def on_event(kind: str, payload) -> None:
        if kind == "plan":
            print("\n[plan]")
            for i, step in enumerate(payload, 1):
                print(f"  {i}. {step}")
        elif kind == "step":
            print(f"\n[step] {payload}")
        elif kind == "result":
            _, result = payload
            preview = result if len(result) < 600 else result[:600] + " ..."
            print(f"  -> {preview}")
        elif kind == "replan":
            if payload.is_complete:
                print("  [replan] complete")
            elif payload.remaining_steps:
                print(f"  [replan] revised remaining: {payload.remaining_steps}")
    return on_event


async def ask(agent, question: str) -> None:
    print("\n" + "=" * 76)
    print(f"Q: {question}")
    print("=" * 76)
    answer = await agent.run(question, on_event=make_printer())
    print("\n--- ANSWER ---")
    print(answer)


async def main() -> None:
    agent = await build_agent()
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    for q in questions:
        await ask(agent, q)


if __name__ == "__main__":
    asyncio.run(main())
