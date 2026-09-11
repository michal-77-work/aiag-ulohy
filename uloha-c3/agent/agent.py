"""The Plan-Execute loop - the whole agent in one function.

    question
       |
       v
     PLAN --> EXECUTE one step --> REPLAN --COMPLETE--> answer
                   ^                  |
                   +----CONTINUE------+   (same plan, or a changed one)
"""

from executor import execute_step
from planner import make_plan
from replanner import replan

MAX_CYCLES = 8  # safety cap: at most this many execute + replan rounds


async def run_agent(question: str, tools: list) -> str:
    plan = await make_plan(question)  # steps still to do; the first one is next
    done_steps = []  # (step, result) pairs that are already done
    replans = 0

    for cycle in range(1, MAX_CYCLES + 1):
        if not plan:
            print("   ⚠️ no steps left, but the replanner is not done - stopping")
            break

        step = plan.pop(0)
        result = await execute_step(question, step, done_steps, tools, cycle)
        done_steps.append((step, result))

        decision = await replan(question, plan, done_steps, cycle)

        if decision.decision == "COMPLETE":
            print(f"\n🏁 COMPLETED · {cycle} cycle(s) · {replans} replan(s)")
            return decision.final_answer

        if decision.new_plan and decision.new_plan != plan:
            replans += 1
            plan = decision.new_plan
            print(f"   🔀 PLAN CHANGED (replan #{replans}) - remaining steps:")
        else:
            print("   ▶ plan unchanged - remaining steps:")
        for number, s in enumerate(plan, start=1):
            print(f"      {number}. {s}")

    print(f"\n🏁 NOT COMPLETED · stopped after {cycle} cycle(s) · {replans} replan(s)")
    found = "\n".join(f"- {s}: {r}" for s, r in done_steps)
    return "I could not finish within the step budget. Here is what I found:\n" + found
