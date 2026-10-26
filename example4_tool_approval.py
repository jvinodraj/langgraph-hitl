"""
Example 4: approve a tool call before it runs.

This is the pattern you actually ship. An agent wants to do something destructive, so the graph asks a human
first and only then calls the tool.

    __start__ -> propose -> guard --(approved)--> tools --> __end__
                               |
                               +----(rejected)--> cancel --> __end__

Note the shape: `guard` does nothing except ask. `tools` does the work. They are separate nodes on purpose -
Example 1 showed what happens when you put a side effect in the same node as the interrupt: it runs twice.

`propose` stands in for a model so this file needs no API key. It always proposes the same tool call, which is
enough to teach the gate. To use a real model, replace `propose` with one node that calls `llm.py` - the guard,
the tool node and the whole approval flow stay exactly as they are.

Run:  python example4_tool_approval.py

No API key needed.
"""
from typing import Annotated

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


# Counts real tool executions, so the demo can prove a rejection never ran anything.
TOOL_RUNS: list[tuple[str, int]] = []


@tool
def delete_records(table: str, older_than_days: int) -> str:
    """Delete rows older than N days from a table. Irreversible."""
    TOOL_RUNS.append((table, older_than_days))
    return f"deleted rows older than {older_than_days} days from '{table}'"


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    approved: bool


def propose(state: State):
    """Stands in for a model: it decides to call a destructive tool."""
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "delete_records",
                "args": {"table": "audit_log", "older_than_days": 90},
                "id": "call_del_1",
            }
        ],
    )
    return {"messages": [call]}


def guard(state: State):
    """Asks. Does nothing else. This is the only node that interrupts."""
    call = state["messages"][-1].tool_calls[0]
    decision = interrupt(
        {
            "action": "approve tool call",
            "tool": call["name"],
            "args": call["args"],
            "reply": "Command(resume=True) to run it, Command(resume=False) to cancel",
        }
    )
    return {"approved": bool(decision)}


def cancel(state: State):
    return {"messages": [AIMessage(content="Cancelled - nothing was deleted.")]}


def route(state: State):
    return "tools" if state["approved"] else "cancel"


def build_graph(checkpointer=None):
    builder = StateGraph(State)
    builder.add_node("propose", propose)
    builder.add_node("guard", guard)
    builder.add_node("tools", ToolNode([delete_records]))
    builder.add_node("cancel", cancel)

    builder.add_edge(START, "propose")
    builder.add_edge("propose", "guard")
    builder.add_conditional_edges("guard", route, path_map={"tools": "tools", "cancel": "cancel"})
    builder.add_edge("tools", END)
    builder.add_edge("cancel", END)

    return builder.compile(checkpointer=checkpointer)


def thread(name: str) -> dict:
    return {"configurable": {"thread_id": name}}


def describe(message) -> str:
    """One readable line per message type."""
    role = {
        "HumanMessage": "human",
        "AIMessage": "agent",
        "ToolMessage": "tool",
        "SystemMessage": "system",
    }.get(type(message).__name__, type(message).__name__)
    calls = getattr(message, "tool_calls", None)
    if calls:
        parts = [f"{c['name']}({', '.join(f'{k}={v!r}' for k, v in c['args'].items())})" for c in calls]
        return f"{role}: wants to call {', '.join(parts)}"
    return f"{role}: {message.content}"


def show(messages) -> None:
    for message in messages:
        print(f"    {describe(message)}")


def main():
    graph = build_graph(checkpointer=MemorySaver())

    # ---------------------------------------------------------------- 1
    print("=" * 72)
    print("1. The agent proposes, the graph stops")
    print("=" * 72)
    approve_config = thread("approve")
    paused = graph.invoke(
        {"messages": [HumanMessage("clean up the audit log")], "approved": False},
        approve_config,
    )

    show(paused["messages"])
    print()
    print(f"  paused at   : {graph.get_state(approve_config).next}")
    print(f"  asking      : {paused['__interrupt__'][0].value}")
    print(f"  tools run   : {len(TOOL_RUNS)}")
    print()

    # ---------------------------------------------------------------- 2
    print("=" * 72)
    print("2. Approve it")
    print("=" * 72)
    approved = graph.invoke(Command(resume=True), approve_config)
    show(approved["messages"])
    print()
    print(f"  tools run   : {len(TOOL_RUNS)}")
    print()

    # ---------------------------------------------------------------- 3
    print("=" * 72)
    print("3. Same graph, same tool, a human says no")
    print("=" * 72)
    reject_config = thread("reject")
    graph.invoke({"messages": [HumanMessage("clean up the audit log")], "approved": False}, reject_config)
    rejected = graph.invoke(Command(resume=False), reject_config)
    show(rejected["messages"])
    print()
    print(f"  tools run   : {len(TOOL_RUNS)}  <- still 1, from the approved thread")
    print("  The audit log is untouched. Nothing was deleted and nothing needs undeleting.")
    print()

    # ---------------------------------------------------------------- 4
    print("=" * 72)
    print("Why the guard is a separate node")
    print("=" * 72)
    print("  Example 1 put interrupt() in the middle of a node that also did work, and the work happened twice.")
    print("  Here the split is explicit:")
    print()
    print("    guard  -> only asks, and asking twice is harmless")
    print("    tools  -> only acts, and only runs once, after a yes")
    print()
    print("  Rule: the node that asks must not be the node that acts.")
    print()
    print("  Alternative: compile(interrupt_before=['tools']) does the same thing with no guard node at all -")
    print("  but then there is no way to say no (see example 3). The guard exists to carry the decision.")


if __name__ == "__main__":
    main()
