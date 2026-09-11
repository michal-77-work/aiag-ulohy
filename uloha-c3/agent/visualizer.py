"""Render the Plan-Execute architecture to graph.png.

    uv run visualizer.py

Our agent is a plain-Python plan->execute->replan loop (not a single compiled
LangGraph), so there is no graph object to introspect. Instead we describe the
architecture as Mermaid and render it with mermaid.ink (needs network).
"""

import base64
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).parent / "graph.png"

MERMAID = """
flowchart TD
    S([START]) --> P["PLANNER<br/>planner.py - list of steps"]
    P --> EX["EXECUTOR<br/>executor.py - tool-calling loop, one step"]

    EX -->|run_sql_query| DB["vendor DB via MCP :8020<br/>read-only SQLite"]
    EX -->|get_current_date| DT["current date<br/>today + quarter"]
    EX -->|web_search| WEB["Tavily web search"]
    DB --> EX
    DT --> EX
    WEB --> EX

    EX --> RP{"REPLANNER<br/>replanner.py - done?"}
    RP -->|no: revise remaining steps| EX
    RP -->|yes: final recommendation| F["FINALIZE<br/>renew / renegotiate / replace"]
    F --> E([END])

    RP -->|step budget exhausted| G["give up<br/>return what was gathered"]
    G --> E
"""


def render(output_path: Path = OUTPUT) -> None:
    # URL-safe base64: standard base64 can contain '/', which breaks the URL (mermaid.ink -> 404).
    encoded = base64.urlsafe_b64encode(MERMAID.encode("utf8")).decode("ascii")
    request = urllib.request.Request(
        f"https://mermaid.ink/img/{encoded}?type=png",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        output_path.write_bytes(response.read())
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    render()
