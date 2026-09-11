"""PLAN: one LLM call that turns the question into a list of steps."""

from pydantic import BaseModel, Field

from model import get_model

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


class Plan(BaseModel):
    steps: list[str] = Field(description="Ordered, specific steps. Each step is one action.")


async def make_plan(question: str) -> list[str]:
    print("\n" + "=" * 70)
    print("📋 PLAN")
    print("=" * 70)

    planner = get_model().with_structured_output(Plan)
    plan = await planner.ainvoke(
        [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": question},
        ]
    )

    print(f"📝 plan ({len(plan.steps)} steps):")
    for number, step in enumerate(plan.steps, start=1):
        print(f"   {number}. {step}")
    return plan.steps
