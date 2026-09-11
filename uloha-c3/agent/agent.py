"""A Plan-Execute agent built with LangChain (no hand-written LangGraph).

The three roles are LangChain pieces, and the plan -> execute -> replan loop is
plain Python in `run()`:

- PLANNER   : an LCEL chain  (prompt | model.with_structured_output(Plan))
- EXECUTOR  : a LangChain create_agent that carries out ONE step using the
              tools (the MCP db tool + Tavily web_search + get_current_date)
- REPLANNER : an LCEL chain that, after each step, either revises the remaining
              plan or declares the task done and returns the final answer.

Why Plan-Execute and not a single ReAct agent: the task needs up-front
decomposition (find Q4 renewals -> assess internal risk -> only THEN research
the flagged ones on the web) and adaptation (dig deeper only where internal
signals warrant it). The replanner is where that adaptation lives.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from pydantic import BaseModel, Field

from model import get_model
from tools import get_current_date, web_search
from mcp_client import load_db_tools

MAX_ITERATIONS = 8  # safety cap on execute/replan cycles


class Plan(BaseModel):
    steps: list[str] = Field(
        description="Ordered, specific steps that together answer the objective. "
        "Each step is one action - a DB query, or a web search for one vendor."
    )


class ReplanDecision(BaseModel):
    is_complete: bool = Field(
        description="True if the steps done so far are enough to answer the objective."
    )
    response: str = Field(
        default="",
        description="The final answer to the user, if is_complete is true. Empty otherwise.",
    )
    remaining_steps: list[str] = Field(
        default_factory=list,
        description="The revised remaining steps if NOT complete. Empty if complete.",
    )


PLANNER_PROMPT = """\
You plan how an analyst agent should answer a question about vendor contracts and risk.

You have two kinds of action available as steps:
- a DATABASE query (an internal SQLite DB of vendors, contracts, incidents), for
  facts like "which contracts renew in Q4", "how many SEV1 incidents per vendor".
- a WEB SEARCH, for external, recent information about a specific vendor
  (outages, breaches, acquisitions, financial trouble, reputation).

Write a short ordered plan (3-6 steps). Good practice:
1. First query the DB to find the relevant vendors/contracts.
2. Then query the DB for internal risk signals (incidents, value, criticality).
3. THEN research on the web only the vendors that look risky or critical - not
   every vendor, to stay focused.
4. End with a step that produces the recommendation.

Each step must be a single concrete action. Do not answer the steps yourself.
"""

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

REPLANNER_PROMPT = """\
You are managing a Plan-Execute loop for a vendor-risk question.

Given the original objective, the original plan, and the steps already executed
with their results, decide:
- If what has been gathered is enough to answer the objective well, set
  is_complete=true and write the final answer in `response`. The answer should,
  per vendor of interest, combine the INTERNAL signals (from the DB) with any
  EXTERNAL findings (from the web) and give a clear recommendation
  (renew / renegotiate / replace / review) with a one-line reason and any source
  URLs found. Note explicitly that this is a recommendation only - nothing in the
  database was changed.
- Otherwise set is_complete=false and give the revised `remaining_steps`
  (e.g. add a targeted web search for a vendor that internal data flagged, or a
  follow-up DB query). Do not repeat steps already done.
"""


class PlanExecuteAgent:
    def __init__(self, tools: list):
        self._model = get_model()
        self._planner = get_model().with_structured_output(Plan)
        self._replanner = get_model().with_structured_output(ReplanDecision)
        self._executor = create_agent(
            model=self._model,
            tools=tools,
            system_prompt=EXECUTOR_PROMPT,
            middleware=[ModelCallLimitMiddleware(run_limit=8, exit_behavior="end")],
        )

    async def _plan(self, objective: str) -> list[str]:
        plan = await self._planner.ainvoke(
            [
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": objective},
            ]
        )
        return plan.steps

    async def _execute_step(self, objective: str, step: str, past: list[tuple[str, str]]) -> str:
        context = "\n".join(f"- {s}\n  -> {r}" for s, r in past) or "(nothing yet)"
        user = (
            f"Overall objective: {objective}\n\n"
            f"Results of previous steps:\n{context}\n\n"
            f"Now execute this step and return only its result:\n{step}"
        )
        result = await self._executor.ainvoke(
            {"messages": [{"role": "user", "content": user}]},
            config={"recursion_limit": 30},
        )
        return str(result["messages"][-1].content).strip()

    async def _replan(
        self, objective: str, original_plan: list[str], past: list[tuple[str, str]]
    ) -> ReplanDecision:
        done = "\n".join(f"- {s}\n  -> {r}" for s, r in past)
        plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(original_plan))
        return await self._replanner.ainvoke(
            [
                {"role": "system", "content": REPLANNER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Objective: {objective}\n\n"
                        f"Original plan:\n{plan_text}\n\n"
                        f"Steps executed so far:\n{done}"
                    ),
                },
            ]
        )

    async def run(self, objective: str, on_event=None) -> str:
        """Run the loop. `on_event(kind, payload)` is an optional progress hook."""

        def emit(kind: str, payload) -> None:
            if on_event:
                on_event(kind, payload)

        plan = await self._plan(objective)
        emit("plan", plan)

        past: list[tuple[str, str]] = []
        remaining = list(plan)

        for _ in range(MAX_ITERATIONS):
            if not remaining:
                # Plan exhausted - force a final replan to compose the answer.
                decision = await self._replan(objective, plan, past)
                emit("replan", decision)
                if decision.response:
                    return decision.response
                remaining = decision.remaining_steps
                if not remaining:
                    break
                continue

            step = remaining.pop(0)
            emit("step", step)
            result = await self._execute_step(objective, step, past)
            emit("result", (step, result))
            past.append((step, result))

            decision = await self._replan(objective, plan, past)
            emit("replan", decision)
            if decision.is_complete and decision.response:
                return decision.response
            if decision.remaining_steps:
                remaining = decision.remaining_steps

        # Ran out of iterations - return what we have rather than raising.
        summary = "\n".join(f"- {s}: {r}" for s, r in past)
        return (
            "I could not fully complete the plan within the step budget. "
            "Here is what I gathered:\n" + summary
        )


async def build_agent() -> PlanExecuteAgent:
    db_tools = await load_db_tools()
    return PlanExecuteAgent(tools=[*db_tools, get_current_date, web_search])
