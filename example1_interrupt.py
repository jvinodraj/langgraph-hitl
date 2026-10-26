"""
Example 1: the primitive.

Session 2 taught a graph to remember. This one teaches it to STOP.

    __start__ -> write -> approve -> __end__

`approve` calls interrupt({...}). The graph pauses there, saves everything, and hands control back to whoever
called invoke(). The return value carries the question under the key `__interrupt__`.

To answer it, call invoke again on the SAME thread, passing Command(resume=<your answer>).

Run:  python example1_interrupt.py

No API key needed. Node bodies are deterministic on purpose - this example is about pausing, not generating.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


class State(TypedDict):
    topic: str
    draft: str
    approved: bool
    note: str


# Records what actually executed. Used at the end to show the re-run behaviour.
TRACE: list[str] = []


def write(state: State):
    """One ordinary node: no interruption, just work."""
    return {"draft": f"A short post about {state['topic']}."}


def approve(state: State):
    """This node asks a human a question and waits."""
    # EVERYTHING ABOVE interrupt() RUNS AGAIN WHEN THE GRAPH RESUMES.
    # In real code this is where an email, a webhook or a database write would go - and it would happen twice.
    TRACE.append("approve() started (a real email would be sent here)")

    answer = interrupt(
        {
            "question": "Approve this draft?",
            "draft": state["draft"],
            "reply": "Command(resume=True) or Command(resume=False)",
        }
    )

    TRACE.append(f"approve() resumed with {answer!r}")
    return {"approved": bool(answer), "note": "approved" if answer else "rejected"}


def build_graph(checkpointer=None):
    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_node("approve", approve)

    builder.add_edge(START, "write")
    builder.add_edge("write", "approve")
    builder.add_edge("approve", END)

    return builder.compile(checkpointer=checkpointer)


def thread(name: str) -> dict:
    """A thread_id is the drawer the paused graph is filed in. Without it, there is nothing to resume."""
    return {"configurable": {"thread_id": name}}


def main():
    graph = build_graph(checkpointer=MemorySaver())

    # ---------------------------------------------------------------- 1
    print("=" * 72)
    print("1. Run until the graph asks a question")
    print("=" * 72)
    config = thread("post-1")
    paused = graph.invoke({"topic": "LangGraph", "draft": "", "approved": False, "note": ""}, config)

    print(f"  invoke returned keys : {list(paused)}")
    question = paused["__interrupt__"][0]
    print(f"  question             : {question.value['question']}")
    print(f"  draft                : {question.value['draft']}")
    print(f"  paused at            : {graph.get_state(config).next}")
    print()
    print("  No node after this ran. The process could exit here and nothing would be lost.")
    print()

    # ---------------------------------------------------------------- 2
    print("=" * 72)
    print("2. Answer it - same thread, Command(resume=True)")
    print("=" * 72)
    finished = graph.invoke(Command(resume=True), config)
    print(f"  result   : {finished}")
    print(f"  paused at: {graph.get_state(config).next or '(nothing left - the run finished)'}")
    print()

    # ---------------------------------------------------------------- 3
    print("=" * 72)
    print("3. A different answer on a different thread")
    print("=" * 72)
    reject_config = thread("post-2")
    graph.invoke({"topic": "Reducers", "draft": "", "approved": False, "note": ""}, reject_config)
    rejected = graph.invoke(Command(resume=False), reject_config)
    print(f"  result   : {rejected}")
    print()

    # ---------------------------------------------------------------- 4
    print("=" * 72)
    print("4. The one thing that bites everybody")
    print("=" * 72)
    TRACE.clear()
    demo_config = thread("rerun-demo")
    graph.invoke({"topic": "Reducers", "draft": "", "approved": False, "note": ""}, demo_config)
    print("  after the first invoke, the node has run once:")
    for line in TRACE:
        print(f"    {line}")
    print()
    graph.invoke(Command(resume=True), demo_config)
    print("  after the resume, the same node has run again from the top:")
    for line in TRACE:
        print(f"    {line}")
    print()
    print("  'approve() started' appears TWICE.")
    print("  On resume, LangGraph re-executes the WHOLE node from the top. interrupt() does not jump back into")
    print("  the middle of the function - it returns the saved answer and the code carries on from there.")
    print()
    print("  So: never put a side effect before interrupt(). Ask first, then act.")
    print()
    print("  The standard fix is a small `ask` node that only interrupts, wired in front of the node that acts.")
    print("  Example 4 does exactly that.")


if __name__ == "__main__":
    main()
