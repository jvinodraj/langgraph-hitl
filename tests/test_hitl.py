"""
tests/test_hitl.py - what a paused graph is supposed to do.

Run:  pytest -q

Every test builds a graph with an in-memory checkpointer (or a throwaway SQLite file), so the suite is fast,
offline and leaves nothing behind.
"""
import sqlite3

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import example1_interrupt
import example2_edit
import example3_breakpoint
import example4_tool_approval
import example5_durable_approval

POST_START = {"topic": "LangGraph", "draft": "", "approved": False, "note": ""}
BRIEF_START = {"brief": "a course called FDE", "draft": "", "final": "", "author": "", "decision": ""}
ORDER_START = {"order_id": "A-1001", "steps_done": []}


@pytest.fixture(autouse=True)
def clean_counters():
    """Example 1 and Example 4 count what ran; reset them so tests cannot leak into each other."""
    example1_interrupt.TRACE.clear()
    example4_tool_approval.TOOL_RUNS.clear()
    yield


# --------------------------------------------------------------------------- interrupt() / Command(resume=...)


def test_interrupt_stops_the_run_and_carries_the_question():
    graph = example1_interrupt.build_graph(MemorySaver())
    config = example1_interrupt.thread("stop")

    result = graph.invoke(dict(POST_START), config)

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["question"] == "Approve this draft?"
    assert graph.get_state(config).next == ("approve",)
    assert result["approved"] is False  # the node never finished


@pytest.mark.parametrize("answer,approved,note", [(True, True, "approved"), (False, False, "rejected")])
def test_resume_with_a_decision(answer, approved, note):
    graph = example1_interrupt.build_graph(MemorySaver())
    config = example1_interrupt.thread(f"resume-{answer}")

    graph.invoke(dict(POST_START), config)
    result = graph.invoke(Command(resume=answer), config)

    assert result["approved"] is approved
    assert result["note"] == note
    assert graph.get_state(config).next == ()


def test_the_node_body_runs_again_on_resume():
    graph = example1_interrupt.build_graph(MemorySaver())
    config = example1_interrupt.thread("rerun")

    graph.invoke(dict(POST_START), config)
    assert len(example1_interrupt.TRACE) == 1

    graph.invoke(Command(resume=True), config)

    started = [line for line in example1_interrupt.TRACE if line.startswith("approve() started")]
    assert len(started) == 2, "the whole node re-executes, not just the part after interrupt()"


# --------------------------------------------------------------------------- static breakpoints


def test_a_static_breakpoint_pauses_without_a_question():
    graph = example3_breakpoint.build_graph(MemorySaver(), interrupt_before=["charge_card"])
    config = example3_breakpoint.thread("static-before")

    result = graph.invoke(dict(ORDER_START), config)

    assert "__interrupt__" not in result
    assert graph.get_state(config).next == ("charge_card",)
    assert result["steps_done"] == ["reserve_stock"]


def test_a_static_breakpoint_resumes_with_none():
    graph = example3_breakpoint.build_graph(MemorySaver(), interrupt_before=["charge_card"])
    config = example3_breakpoint.thread("static-resume")

    graph.invoke(dict(ORDER_START), config)
    result = graph.invoke(None, config)

    assert result["steps_done"] == ["reserve_stock", "charge_card", "ship"]
    assert graph.get_state(config).next == ()


# --------------------------------------------------------------------------- the resume value is data


def test_resume_can_replace_the_text():
    graph = example2_edit.build_graph(MemorySaver())
    config = example2_edit.thread("edit")

    graph.invoke(dict(BRIEF_START), config)
    result = graph.invoke(
        Command(resume={"decision": "edit", "text": "Learn by building, not by reading slides."}),
        config,
    )

    assert result["decision"] == "edit"
    assert result["final"] == "Learn by building, not by reading slides."
    assert result["author"] == "human"


def test_resume_can_reject_the_draft():
    graph = example2_edit.build_graph(MemorySaver())
    config = example2_edit.thread("reject")

    graph.invoke(dict(BRIEF_START), config)
    result = graph.invoke(Command(resume={"decision": "reject"}), config)

    assert result["decision"] == "reject"
    assert result["final"] == ""


# --------------------------------------------------------------------------- the tool approval guard


def test_approved_tool_runs_exactly_once():
    graph = example4_tool_approval.build_graph(MemorySaver())
    config = example4_tool_approval.thread("approve")

    graph.invoke({"messages": [HumanMessage("clean up the audit log")], "approved": False}, config)
    assert example4_tool_approval.TOOL_RUNS == []

    result = graph.invoke(Command(resume=True), config)

    assert example4_tool_approval.TOOL_RUNS == [("audit_log", 90)]
    assert any(isinstance(message, ToolMessage) for message in result["messages"])


def test_rejected_tool_never_runs():
    graph = example4_tool_approval.build_graph(MemorySaver())
    config = example4_tool_approval.thread("reject-tool")

    graph.invoke({"messages": [HumanMessage("clean up the audit log")], "approved": False}, config)
    result = graph.invoke(Command(resume=False), config)

    assert example4_tool_approval.TOOL_RUNS == []
    assert not any(isinstance(message, ToolMessage) for message in result["messages"])


# --------------------------------------------------------------------------- durability


def test_a_pending_approval_survives_a_new_connection(tmp_path):
    db_path = tmp_path / "approvals.db"

    connection = sqlite3.connect(db_path, check_same_thread=False)
    graph = example4_tool_approval.build_graph(SqliteSaver(connection))
    config = example4_tool_approval.thread("durable")
    graph.invoke({"messages": [HumanMessage("clean up the audit log")], "approved": False}, config)
    connection.close()  # the asking process is gone

    connection = sqlite3.connect(db_path, check_same_thread=False)
    graph = example4_tool_approval.build_graph(SqliteSaver(connection))
    snapshot = graph.get_state(config)

    assert snapshot.next == ("guard",)
    question = example5_durable_approval.pending_question(snapshot)
    assert question["tool"] == "delete_records"

    connection.close()
