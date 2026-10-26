"""
Example 3: static breakpoints - the blunt tool.

Examples 1 and 2 put interrupt() inside a node. There is a second way to pause, and it needs no code in the node
at all: tell compile() where to stop.

    __start__ -> reserve_stock -> charge_card -> ship -> __end__

Same pipeline as Session 2's example 4, where charge_card crashed and a new process resumed it. Here nobody
crashes - we stop there on purpose, before the payment is taken.

    compile(interrupt_before=["charge_card"])

Run:  python example3_breakpoint.py

No API key needed.
"""
import operator
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class State(TypedDict):
    order_id: str
    steps_done: Annotated[list[str], operator.add]


def reserve_stock(state: State):
    print("  reserve_stock  -> stock reserved")
    return {"steps_done": ["reserve_stock"]}


def charge_card(state: State):
    print("  charge_card    -> payment taken")
    return {"steps_done": ["charge_card"]}


def ship(state: State):
    print("  ship           -> dispatched")
    return {"steps_done": ["ship"]}


def build_graph(checkpointer=None, interrupt_before=None, interrupt_after=None):
    """The nodes are unchanged. The breakpoints are a compile-time setting."""
    builder = StateGraph(State)
    builder.add_node("reserve_stock", reserve_stock)
    builder.add_node("charge_card", charge_card)
    builder.add_node("ship", ship)

    builder.add_edge(START, "reserve_stock")
    builder.add_edge("reserve_stock", "charge_card")
    builder.add_edge("charge_card", "ship")
    builder.add_edge("ship", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )


def thread(name: str) -> dict:
    return {"configurable": {"thread_id": name}}


def show_pause(graph, result: dict, config: dict) -> None:
    snapshot = graph.get_state(config)
    print(f"  steps done     : {snapshot.values['steps_done']}")
    print(f"  paused at      : {snapshot.next}")
    print(f"  '__interrupt__' in the return value? {'__interrupt__' in result}")
    print()


def main():
    start = {"order_id": "A-1001", "steps_done": []}

    # ---------------------------------------------------------------- 1
    print("=" * 72)
    print("1. interrupt_before=['charge_card'] - stop before the payment")
    print("=" * 72)
    graph = build_graph(MemorySaver(), interrupt_before=["charge_card"])
    config = thread("before-charge")

    result = graph.invoke(dict(start), config)
    show_pause(graph, result, config)

    print("  Note there is no question and no answer channel. `next` is the only signal.")
    print("  To approve, resume with invoke(None, config) - no value is passed:")
    print()
    finished = graph.invoke(None, config)
    print(f"  steps done     : {finished['steps_done']}")
    print()

    # ---------------------------------------------------------------- 2
    print("=" * 72)
    print("2. interrupt_after=['reserve_stock'] - stop after the stock is held")
    print("=" * 72)
    graph2 = build_graph(MemorySaver(), interrupt_after=["reserve_stock"])
    config2 = thread("after-stock")

    result2 = graph2.invoke(dict(start), config2)
    show_pause(graph2, result2, config2)
    print("  Identical `next` to case 1, because the two nodes are adjacent. Before charge_card and after")
    print("  reserve_stock are the same moment in time.")
    print()
    graph2.invoke(None, config2)
    print()

    # ---------------------------------------------------------------- 3
    print("=" * 72)
    print("3. The limitation nobody mentions")
    print("=" * 72)
    graph3 = build_graph(MemorySaver(), interrupt_before=["charge_card"])
    config3 = thread("abandoned")
    graph3.invoke(dict(start), config3)

    print("  Suppose the approver looks at it and decides NO. There is nothing to send.")
    print("  A static breakpoint has no return value - your options are:")
    print()
    print("    - resume it           -> invoke(None, config)      (yes)")
    print("    - never resume it     -> the thread sits paused forever (\"no\" by neglect)")
    print()
    stuck = graph3.get_state(config3)
    print(f"  The abandoned order still says: next={stuck.next} steps_done={stuck.values['steps_done']}")
    print()
    print("  It cannot record WHY it stopped, who looked at it, or what they decided. In a real system that")
    print("  order is now in limbo and no dashboard can tell a pending approval from a forgotten one.")
    print()

    # ---------------------------------------------------------------- 4
    print("=" * 72)
    print("So when is a static breakpoint the right tool?")
    print("=" * 72)
    print("  Good for:   a debugger-style pause, a checkpoint to inspect logging or cost, a demo")
    print("  Bad for:    an approval that can be refused, an edit, anything needing an answer")
    print()
    print("  Rule of thumb: if a human has to DECIDE something, use interrupt() (examples 1, 2 and 4).")
    print("  If you only need a human to LOOK, interrupt_before / interrupt_after is one line and no code churn.")


if __name__ == "__main__":
    main()
