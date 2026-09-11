"""Agent-side LangChain tools: web search (Tavily) and today's date.

Tavily is a LangChain-native search integration aimed at agents. It needs
TAVILY_API_KEY in the environment (free tier is enough here). We wrap it rather
than exposing it raw so we control result count and content size, and so a
search failure comes back as text the agent can react to instead of an
exception that kills the run.
"""

import calendar
import os
from datetime import date

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv()

MAX_RESULTS = 4
SNIPPET_CHARS = 500

_tavily = TavilySearch(max_results=MAX_RESULTS, api_key=os.getenv("TAVILY_API_KEY"))


@tool
def web_search(query: str) -> str:
    """Search the web for recent, external information about a company or topic
    (news, outages, breaches, acquisitions, reviews).

    Use specific, targeted queries. Prefer several narrow searches over one
    broad one.

    Args:
        query: A search query, phrased as you would type it into a search box.
    """
    try:
        result = _tavily.invoke({"query": query})
    except Exception as exc:
        return f"Search failed: {type(exc).__name__}: {exc}. Try a different query."

    results = result.get("results", []) if isinstance(result, dict) else []
    if not results:
        return "No results for that query. Try different wording."

    lines = []
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = (r.get("content") or "")[:SNIPPET_CHARS]
        lines.append(f"{title}\n{url}\n{content}")
    return "\n\n".join(lines)


# The model has no clock; a date written into the prompt goes stale.
@tool
def get_current_date() -> str:
    """Return today's date and the current calendar quarter.

    Call this before answering anything relative to today - "this quarter",
    "Q4" without a year, "recent", "last 30 days", "upcoming renewals".
    """
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    last_month = 3 * quarter
    start = date(today.year, last_month - 2, 1)
    end = date(today.year, last_month, calendar.monthrange(today.year, last_month)[1])
    return (
        f"Today is {today.isoformat()} ({today.strftime('%A')}). "
        f"Current quarter: Q{quarter} {today.year} ({start.isoformat()} to {end.isoformat()})."
    )
