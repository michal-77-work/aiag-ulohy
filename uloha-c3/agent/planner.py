"""PLAN: one LLM call that turns the question into a list of steps."""

from pydantic import BaseModel, Field

from model import get_model

PLANNER_PROMPT = """\
You plan how an analyst agent should answer a question about vendor contracts and risk.

You have two kinds of action available as steps:
- a DATABASE query against the internal SQLite DB. It contains ONLY:
    vendors   - name, category, country, criticality (low/medium/high/critical)
    contracts - service, annual_value, renewal_quote (the price quoted for the
                next term), renewal_date, auto_renew
    incidents - date, type (outage/sla_breach/security/data_quality), severity (SEV1-3)
- a WEB SEARCH, for external, recent news about one specific vendor
  (outages, breaches, acquisitions, financial trouble).

Plan only what the question needs:
- A factual question (e.g. "which contracts renew in Q4") may need just one DB
  step - no risk analysis, no web search.
- A risk or recommendation question needs a short plan (3-5 steps), for example:
  1. Query the DB for the relevant vendors and contracts (with vendor names).
  2. Query the DB for internal risk signals: incidents per vendor in the last
     ~90 days and the price change (renewal_quote vs annual_value).
  3. Search the web only for the vendors that look risky - not every vendor.
  4. Produce the recommendation.

Only plan with data that exists in the DB - do not invent metrics that are not
there. Each step must be a single concrete action. Do not answer the steps yourself.
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
