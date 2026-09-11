"""Ask the vendor-risk agent questions.

    uv run seed.py            # in ../mcp_server, once - builds vendors.db
    uv run -m server          # in ../mcp_server - start the MCP server
    uv run main.py            # the scripted questions
    uv run main.py "your question"
"""

import asyncio
import sys

from agent import run_agent
from mcp_client import load_db_tools
from tools import get_current_date, web_search

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


async def main() -> None:
    # The log uses emojis; on Windows the output is often not UTF-8 by default.
    sys.stdout.reconfigure(encoding="utf-8")

    db_tools = await load_db_tools()  # from the MCP server
    tools = db_tools + [get_current_date, web_search]
    print(f"🔧 {len(tools)} tools: {[tool.name for tool in tools]}")

    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    for question in questions:
        print("\n" + "#" * 70)
        print(f"❓ {question}")
        print("#" * 70)

        answer = await run_agent(question, tools)

        print("\n💡 ANSWER:")
        print(answer)


if __name__ == "__main__":
    asyncio.run(main())
