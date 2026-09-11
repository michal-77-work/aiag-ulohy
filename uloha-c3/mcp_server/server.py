"""Vendor DB as a Streamable HTTP MCP server.

Same pattern as uloha-c2/mcp_server and 2_MCP/.../my_server - one readable
file - but backed by the local SQLite vendors.db through the read-only safety
layer in db.py. Exposes one tool, run_sql_query, which the LangChain agent in
../agent consumes via langchain-mcp-adapters.
"""

import json
import contextlib
from collections.abc import AsyncIterator

import uvicorn

from mcp.server.lowlevel import Server
import mcp.types as types
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from db import UnsafeQuery, get_schema, run_query

PORT = 8020

SCHEMA_HINT = (
    "Vendor-risk database (SQLite). Three tables:\n"
    "  vendors(vendor_id, name, category, country, criticality)  "
    "criticality in (low, medium, high, critical)\n"
    "  contracts(contract_id, vendor_id, service, annual_value, start_date, "
    "renewal_date, auto_renew, status)  dates are ISO 'YYYY-MM-DD', auto_renew is 0/1\n"
    "  incidents(incident_id, vendor_id, date, type, severity, description)  "
    "type in (outage, sla_breach, security, data_quality), severity in (SEV1, SEV2, SEV3)"
)


def serve():
    server = Server("mcp-vendor-db")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="run_sql_query",
                description=(
                    "Run a read-only SQL query against the vendor-risk SQLite "
                    "database and get the resulting rows back as JSON.\n\n"
                    + SCHEMA_HINT
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
            types.Tool(
                name="describe_schema",
                description="Return the full DB schema (CREATE statements + sample rows).",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        print("CALL TOOL:", name, arguments)

        if name == "describe_schema":
            result = {"schema": get_schema()}
        elif name == "run_sql_query":
            try:
                columns, rows = run_query(arguments["query"])
                result = {
                    "row_count": len(rows),
                    "columns": columns,
                    "rows": [dict(zip(columns, r)) for r in rows],
                }
            except UnsafeQuery as exc:
                result = {"error": f"Rejected by the safety check: {exc}"}
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}
        else:
            result = {"error": f"Unknown tool: {name}"}

        print("Result:", result)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    session_manager = StreamableHTTPSessionManager(
        app=server, json_response=True, event_store=None, stateless=True
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            print(f"Vendor DB MCP server started (Streamable HTTP) on :{PORT}/mcp/")
            try:
                yield
            finally:
                print("Shutting down...")

    starlette_app = Starlette(
        debug=True,
        routes=[Mount("/mcp", app=handle_streamable_http)],
        lifespan=lifespan,
    )

    uvicorn.run(starlette_app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    print("Starting Vendor DB MCP server...")
    try:
        serve()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Cleaning up before exit...")
