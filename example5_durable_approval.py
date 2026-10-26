"""
Example 5: an approval that outlives the process.

Examples 1 to 4 kept the pause in RAM. In production the approver is a different person on a different day, so the
pending question has to survive the process that asked it.

This is Example 4's graph with one change: SqliteSaver instead of MemorySaver. Nothing about the nodes, the guard
or the interrupt changes.

    python example5_durable_approval.py              # process 1: propose, pause, exit
    python example5_durable_approval.py --approve    # process 2: resume, tool runs
    python example5_durable_approval.py --reject     # process 2: the other answer
    python example5_durable_approval.py --reset      # start over

The database and its thread live in .data/ and are gitignored.

No API key needed.
"""
import json
import sqlite3
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from example4_tool_approval import build_graph, describe, thread


DATA_DIR = Path(__file__).resolve().parent / ".data"
DB_PATH = DATA_DIR / "approvals.db"
THREAD_ID = "audit-cleanup"


def pending_question(snapshot):
    """The interrupt payload is checkpointed too - recover it from the saved task."""
    for task in snapshot.tasks:
        for intr in task.interrupts:
            return intr.value
    return None


def reset() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    print("Removed the saved approval. The next run starts fresh.")


def main():
    if "--reset" in sys.argv:
        reset()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    graph = build_graph(SqliteSaver(conn))
    config = thread(THREAD_ID)

    snapshot = graph.get_state(config)

    # ------------------------------------------------ process 1: nothing saved yet
    if not snapshot.values:
        print("=" * 72)
        print("Process 1 - propose, pause, exit")
        print("=" * 72)
        paused = graph.invoke(
            {"messages": [HumanMessage("clean up the audit log")], "approved": False},
            config,
        )
        for message in paused["messages"]:
            print(f"  {describe(message)}")
        print()
        print(f"  paused at : {graph.get_state(config).next}")
        print(f"  question  : {paused['__interrupt__'][0].value['action']}")
        print()
        print("  This process is about to exit. The question is now a row in .data/approvals.db.")
        print()
        print("  Now decide, in a NEW process:")
        print("      python example5_durable_approval.py --approve")
        print("      python example5_durable_approval.py --reject")
        conn.close()
        return

    # ------------------------------------------------ process 2: still waiting
    if snapshot.next:
        print("=" * 72)
        print("Process 2 - a pending approval found in the database")
        print("=" * 72)
        print(f"  paused at : {snapshot.next}")
        print("  question recovered from the database:")
        print("\n".join("    " + line for line in json.dumps(pending_question(snapshot), indent=2).splitlines()))
        print(f"  approved so far : {snapshot.values['approved']}")
        print()

        if "--approve" in sys.argv:
            answer = True
        elif "--reject" in sys.argv:
            answer = False
        else:
            print("  No decision given. Pass --approve or --reject.")
            conn.close()
            return

        print(f"  resuming with Command(resume={answer}) ...")
        print()
        result = graph.invoke(Command(resume=answer), config)
        for message in result["messages"]:
            print(f"  {describe(message)}")
        print()
        print(f"  finished, next = {graph.get_state(config).next or '(nothing left)'}")
        conn.close()
        return

    # ------------------------------------------------ already answered
    print("=" * 72)
    print("This approval was already answered")
    print("=" * 72)
    print(f"  approved : {snapshot.values['approved']}")
    for message in snapshot.values["messages"]:
        print(f"  {describe(message)}")
    print()
    print("  Run  python example5_durable_approval.py --reset  to start over.")
    conn.close()


if __name__ == "__main__":
    main()
