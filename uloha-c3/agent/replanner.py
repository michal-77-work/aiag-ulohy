"""REPLAN: after each step, decide - COMPLETE (answer now) or CONTINUE (with the remaining plan)."""

from typing import Literal

from pydantic import BaseModel, Field

from model import get_model

REPLANNER_PROMPT = """\
You are the REPLANNER of a Plan-Execute agent answering a vendor-risk question.

You see the question, the steps already done with their results, and the steps
still planned. Decide:
- COMPLETE: the results are enough to answer. Write the answer in final_answer:
  per vendor of interest, combine the INTERNAL signals (from the DB) with any
  EXTERNAL findings (from the web) and give a clear recommendation
  (renew / renegotiate / replace / review) with a one-line reason and any source
  URLs. Say explicitly that this is a recommendation only - nothing in the
  database was changed.
- CONTINUE: more work is needed. Put the REMAINING steps in new_plan - keep the
  planned steps if they are still right, or change them (e.g. add a web search
  for a vendor the DB flagged, drop a step that is no longer needed). Never
  repeat a step that is already done.

Always explain your decision in one line in `reason`.
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
