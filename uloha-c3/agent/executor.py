"""EXECUTE: carry out ONE plan step with a tool-calling loop.

    model --asks for a tool--> we run the tool --result--> model ... --no tool call--> step done
"""

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from model import get_model

MAX_MODEL_CALLS = 8  # per step - stops a model that would keep calling tools forever

EXECUTOR_PROMPT = """\
You are a procurement-analyst agent executing ONE step of a larger plan.

Tools:
- run_sql_query / describe_schema : the internal vendor database (read-only,
  SQLite). Dates are stored as ISO 'YYYY-MM-DD' strings - filter them with ISO
  string literals (renewal_date BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD').
- get_current_date : today's date and the current quarter. You do NOT know
  today's date otherwise - call this before resolving anything relative to
  today ("Q4" without a year, "this quarter", "recent", "last 30 days",
  "upcoming"). Quarters: Q1 Jan-Mar, Q2 Apr-Jun, Q3 Jul-Sep, Q4 Oct-Dec. A
  quarter named without a year means the nearest one that has not ended yet.
- web_search : recent external information about a specific vendor.

Rules:
- Use the tools to actually get data. Never invent numbers, vendors or news.
- The database is READ-ONLY. If a step implies changing data, do not attempt it;
  report what the data shows instead. You only advise, you never act.
- When you web_search, keep the source URLs and include them in your result.
- Return ONLY the result of THIS step, concisely, for the next step to build on.
"""


def tool_result_as_text(result) -> str:
    # MCP tools return a list of content blocks, our own tools return a string.
    if isinstance(result, list):
        return "\n".join(block.get("text", "") for block in result if isinstance(block, dict))
    return str(result)


async def execute_step(question: str, step: str, done_steps: list, tools: list, cycle: int) -> str:
    print("\n" + "=" * 70)
    print(f"🚀 EXECUTE   (cycle {cycle})")
    print("=" * 70)
    print(f"   ▶ step: {step}")

    tools_by_name = {tool.name: tool for tool in tools}
    model = get_model().bind_tools(tools)

    previous = "\n".join(f"- {s}\n  -> {r}" for s, r in done_steps) or "(nothing yet)"
    messages = [
        SystemMessage(EXECUTOR_PROMPT),
        HumanMessage(
            f"Overall question: {question}\n\n"
            f"Results of previous steps:\n{previous}\n\n"
            f"Now execute this step and return only its result:\n{step}"
        ),
    ]

    for model_call in range(1, MAX_MODEL_CALLS + 1):
        print(f"   🤖 model call {model_call}/{MAX_MODEL_CALLS}")
        response = await model.ainvoke(messages)
        messages.append(response)

        # No tool call means the model has answered - the step is done.
        if not response.tool_calls:
            answer = str(response.content)
            print(f"   💬 step result: {answer[:500]}")
            return answer

        for call in response.tool_calls:
            print(f"   🔧 {call['name']}({call['args']})")
            try:
                result = tool_result_as_text(await tools_by_name[call["name"]].ainvoke(call["args"]))
            except Exception as exc:
                result = f"Tool error: {exc}"
            print(f"      ↳ {result[:300]}")
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    print(f"   ⏰ step not finished within {MAX_MODEL_CALLS} model calls")
    return f"(step not finished within {MAX_MODEL_CALLS} model calls)"
