import os
import json
import contextlib
from collections.abc import AsyncIterator

import psycopg2
import psycopg2.extras
import uvicorn

# MCP
from mcp.server.lowlevel import Server
import mcp.types as types
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# ---------------------------------
# Database connection (read-only role by default)
# ---------------------------------
DB_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": os.environ.get("PGPORT", "5432"),
    "user": os.environ.get("PGUSER", "helpdesk_ro"),
    "password": os.environ.get("PGPASSWORD", "Heslo_1234"),
    "dbname": os.environ.get("PGDATABASE", "helpdesk"),
}

# The schema is small and fixed, so we hand it to the LLM in the tool description
# instead of exposing a separate introspection tool.
TABLE_SCHEMA = (
    "Table 'tickets' (IT helpdesk tickets):\n"
    "  id           INTEGER    primary key\n"
    "  subject      TEXT\n"
    "  customer     TEXT\n"
    "  category     TEXT       (Network, Hardware, Software, Account Access, Email, Printer)\n"
    "  priority     TEXT       (Low, Medium, High, Critical)\n"
    "  status       TEXT       (Open, In Progress, Resolved, Closed)\n"
    "  assigned_to  TEXT       agent name, NULL if unassigned\n"
    "  created_at   TIMESTAMP\n"
    "  resolved_at  TIMESTAMP  NULL until the ticket is resolved/closed\n"
)


def run_sql_query(query: str) -> dict:
    """Run one read-only SELECT/WITH query and return the rows.

    A fresh connection per call keeps this simple and sidesteps any
    aborted-transaction pooling issues. Writes are also blocked at the DB
    level by the read-only Postgres role.
    """
    q = query.strip().rstrip(";").strip()
    if not q.lower().startswith(("select", "with")):
        return {"error": "Only read-only SELECT/WITH queries are allowed."}

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(q)
            rows = cur.fetchall()
        return {"row_count": len(rows), "rows": rows}
    except psycopg2.Error as e:
        return {"error": str(e).strip()}
    finally:
        conn.close()


def serve():
    server = Server("mcp-helpdesk-db")

    # ---------------------------------
    # Tools
    # ---------------------------------

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="run_sql_query",
                description=(
                    "Run a read-only SQL query against the IT helpdesk PostgreSQL "
                    "database and get the resulting rows back as JSON.\n\n"
                    + TABLE_SCHEMA
                ),
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A single read-only SQL SELECT statement.",
                        }
                    },
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        print("CALL TOOL:", name, arguments)

        if name == "run_sql_query":
            result = run_sql_query(arguments["query"])
        else:
            result = {"error": f"Unknown tool: {name}"}

        print("Result:", result)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    # ---------------------------------
    # Streamable HTTP transport (same pattern as 2_MCP/.../my_server)
    # ---------------------------------
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        event_store=None,
        stateless=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            print("Helpdesk DB MCP server started (Streamable HTTP)!")
            try:
                yield
            finally:
                print("Shutting down...")

    starlette_app = Starlette(
        debug=True,
        routes=[Mount("/mcp", app=handle_streamable_http)],
        lifespan=lifespan,
    )

    port = int(os.environ.get("PORT", "8010"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    print("Starting Helpdesk DB MCP server...")
    try:
        serve()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Cleaning up before exit...")
