"""REPLAN: after each step, decide - COMPLETE (answer now) or CONTINUE (with the remaining plan)."""

from typing import Literal

from pydantic import BaseModel, Field

from model import get_model

REPLANNER_PROMPT = """\
You are the REPLANNER of a Plan-Execute agent answering a question about vendor
contracts and risk.

You see the question, the steps already done with their results, and the steps
still planned. Decide:
- COMPLETE: the results are enough to answer. Write the answer in final_answer.
- CONTINUE: more work is needed. Put the REMAINING steps in new_plan - keep the
  planned steps if they are still right, or change them (e.g. add a query or a
  web search that is missing, drop a step that is no longer needed). Never
  repeat a step that is already done.

Always explain your decision in one line in `reason`.

Only facts from the steps done count. Never state anything about a vendor that
no step returned - if something you need is missing, CONTINUE and add a step.

How to write final_answer:
- Answer exactly what was asked. A factual question (e.g. a list of contracts)
  gets the facts only - no recommendations.
- If the question asks about risk or what to do, write one entry per vendor, by
  NAME, with the recommendation, the internal signals behind it and the external
  findings, and follow these rules:
    * Before recommending for a vendor, its incidents in the last ~90 days and
      its renewal_quote vs annual_value must have been queried.
    * renegotiate / replace : SEV1 incidents or an SLA breach in the last ~90
                              days (do not let such a contract auto-renew)
      review pricing        : renewal_quote more than 10% above annual_value
      renew                 : none of the above; a single minor (SEV3) incident
                              does not change this
    * Every vendor you recommend to renegotiate, replace or review pricing must
      have been web-searched before you choose COMPLETE.
    * External findings are ONLY what a web_search in the steps done returned
      about that exact company, with source URLs. Write "no vendor-specific news
      found" if it was searched but nothing was about it, and "not searched" if
      it was not searched.
    * A web finding changes the recommendation only if it is clearly about that
      exact company and describes something serious (breach, outage, bankruptcy,
      acquisition).
    * End with: this is a recommendation only - nothing in the database was changed.
"""


class ReplanDecision(BaseModel):
    decision: Literal["COMPLETE", "CONTINUE"]
    reason: str = Field(description="One line: why this decision.")
    new_plan: list[str] = Field(default_factory=list, description="The remaining steps, if CONTINUE.")
    final_answer: str = Field(default="", description="The answer to the user, if COMPLETE.")


async def replan(question: str, plan: list[str], done_steps: list, cycle: int) -> ReplanDecision:
    print("\n" + "=" * 70)
    print(f"🔄 REPLAN   (cycle {cycle})")
    print("=" * 70)

    done = "\n".join(f"- {s}\n  -> {r}" for s, r in done_steps)
    planned = "\n".join(f"{n}. {s}" for n, s in enumerate(plan, start=1)) or "(none)"

    replanner = get_model().with_structured_output(ReplanDecision)
    decision = await replanner.ainvoke(
        [
            {"role": "system", "content": REPLANNER_PROMPT},
            {
                "role": "user",
                "content": f"Question: {question}\n\nSteps done:\n{done}\n\nSteps still planned:\n{planned}",
            },
        ]
    )

    print(f"   decision: {decision.decision} — {decision.reason}")
    return decision
