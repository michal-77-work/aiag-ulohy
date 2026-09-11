"""Load the database tools from our MCP server.

The vendor DB is not a framework-specific tool - it is an MCP server
(../mcp_server, Streamable HTTP). We pull its tools in as LangChain tools with
langchain-mcp-adapters, so the executor agent sees run_sql_query / describe_schema
exactly like any other LangChain tool.
"""

import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

MCP_URL = os.getenv("VENDOR_DB_MCP_URL", "http://localhost:8020/mcp/")


async def load_db_tools() -> list:
    """Connect to the vendor DB MCP server and return its tools as LangChain
    tools."""
    client = MultiServerMCPClient(
        {
            "vendor_db": {
                "url": MCP_URL,
                "transport": "streamable_http",
            }
        }
    )
    return await client.get_tools()
