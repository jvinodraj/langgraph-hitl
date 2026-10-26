"""
Example 2: the answer is data, not just yes or no.

Example 1 resumed with True/False. A resume value can be any JSON-shaped thing, and that makes the human a
collaborator instead of a rubber stamp:

    __start__ -> write -> review -> __end__

`review` sends the draft out with a question, and what comes back decides three different outcomes:

    Command(resume={"decision": "approve"})                     -> the agent's text is published
    Command(resume={"decision": "edit", "text": "..."})         -> the human's text is published
    Command(resume={"decision": "reject"})                      -> nothing is published

The same graph, the same thread, three endings. Nothing in the node's control flow changes - only the payload.

Run:  python example2_edit.py

No API key needed.
"""
import json

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


class State(TypedDict):
    brief: str
    draft: str          # what the agent wrote
    final: str          # what actually gets published
    author: str         # "agent" or "human" - who wrote the final text
    decision: str       # "approve", "edit" or "reject"


def write(state: State):
    return {"draft": f"Marketing copy for: {state['brief']}. Built with LangGraph."}


def review(state: State):
    answer = interrupt(
        {
            "question": "Approve, edit or reject?",
            "draft": state["draft"],
            "reply_with": {
                "decision": "approve | edit | reject",
                "text": "(only when decision is 'edit') your replacement text",
            },
        }
    )

    # The node trusts nothing: a malformed answer is treated as a rejection.
    decision = answer.get("decision", "reject") if isinstance(answer, dict) else "reject"

    if decision == "edit":
        return {"final": answer.get("text", ""), "author": "human", "decision": "edit"}
    if decision == "approve":
        return {"final": state["draft"], "author": "agent", "decision": "approve"}
    return {"final": "", "author": "agent", "decision": "reject"}


def build_graph(checkpointer=None):
    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_node("review", review)

    builder.add_edge(START, "write")
    builder.add_edge("write", "review")
    builder.add_edge("review", END)

    return builder.compile(checkpointer=checkpointer)


def thread(name: str) -> dict:
    return {"configurable": {"thread_id": name}}


def run_case(graph, name: str, answer: dict) -> dict:
    """Start a fresh thread, stop at the review, then resume with `answer`."""
    config = thread(name)
    graph.invoke(
        {"brief": "a course called FDE", "draft": "", "final": "", "author": "", "decision": ""},
        config,
    )
    return graph.invoke(Command(resume=answer), config)


def show(label: str, result: dict) -> None:
    print(f"  {label}")
    print(f"    decision : {result['decision']}")
    print(f"    author   : {result['author']}")
    print(f"    final    : {result['final']!r}")
    print()


def main():
    graph = build_graph(checkpointer=MemorySaver())

    print("=" * 72)
    print("What the human sees when the graph asks")
    print("=" * 72)
    config = thread("peek")
    paused = graph.invoke(
        {"brief": "a course called FDE", "draft": "", "final": "", "author": "", "decision": ""},
        config,
    )
    print(json.dumps(paused["__interrupt__"][0].value, indent=2))
    print()

    print("=" * 72)
    print("Three answers to the same question")
    print("=" * 72)
    show("approve", run_case(graph, "case-approve", {"decision": "approve"}))
    show(
        "edit",
        run_case(
            graph,
            "case-edit",
            {
                "decision": "edit",
                "text": "Marketing copy for a course called FDE. Learn by building, not by reading slides.",
            },
        ),
    )
    show("reject", run_case(graph, "case-reject", {"decision": "reject"}))

    print("=" * 72)
    print("Why this matters")
    print("=" * 72)
    print("  'approve' vs 'edit' is the difference between a signature and a correction. Both are one resume call.")
    print("  The graph did not change shape for any of the three cases - the branch lives in the payload, so you")
    print("  can add a fourth outcome tomorrow without touching the topology.")
    print()
    print("  `author` is in the state so the record shows who was responsible for the published text. In a real")
    print("  system that field is your audit trail.")


if __name__ == "__main__":
    main()
