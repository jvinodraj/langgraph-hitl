# langgraph-hitl

Session 3 of LangGraph, for the FDE C4/C5 cohort. The companion repo to [langgraph-graphs](../langgraph-graphs) and
[langgraph-persistence](../langgraph-persistence), and to the *LangGraph Pre-Read: What, Why, Nodes, Edges and Shared
State* document.

Session 2 taught a graph to remember. This one teaches it to **stop and ask**.

Every example runs with **no API key**.

| Session | Repo | Topic |
|---|---|---|
| 1 | hopscotch-s1-openai-chatbot | Raw `openai` SDK + Streamlit, list-of-dicts history |
| 2 | hopscotch-s2-langchain-chatbot | LangChain: prompts, chains, memory, imperative triage |
| 3 | hopscotch-s3-lcel-chatbot | Runnables, LCEL, Parallel, Branch, streaming |
| 4 | langgraph-graphs | State, nodes, edges, reducers, branching, loops |
| 5 | langgraph-persistence | Checkpoints, threads, resume, time travel |
| **6** | **langgraph-hitl (you are here)** | **Pause, ask a human, resume with the answer** |

## The one line that holds it all

> **A checkpointed graph is a process. A process can wait for a person.**

## Where Session 2 stops

Session 2 could save a graph's position. It had no way to *use* that position on purpose.

| You need | Session 2 graph | With `interrupt()` |
|---|---|---|
| Stop mid-run | only by crashing | on purpose, at a chosen line |
| Ask a human something | no channel at all | `interrupt(payload)` |
| Receive an answer | no | `Command(resume=value)` |
| Let a human say no | not possible | branch on the answer |
| Let a human edit the output | `update_state` before resuming | the resume value itself |
| Resume in a different process | yes - after a crash | yes - after an approval |
| Know what was asked, later | no | the question is checkpointed too |

**Rule of thumb:** if a step is irreversible or expensive, put a person in front of it.

## The analogy

Session 2 was the filing cabinet: every completed step filed a photocopy, stamped with the next desk.

Session 3 is the **pink slip stapled to the case file**.

- Most desks just do their work. One desk has a slip that says *"needs a manager's signature"*.
- The clerk does not guess, does not sign it themselves, and does not stand there waiting. They put the file in the
  **out-tray**, write down which desk was next, and go home.
- The next morning a manager pulls the file, reads the slip, and signs it. **The same file, a different person, a
  different day.**
- The clerk then picks up exactly where the file stopped. The desks that already ran do not run again.

The pink slip is `interrupt()`. The signature is `Command(resume=...)`. The out-tray is the checkpointer.

## Concepts map

| Concept | Where to see it |
|---|---|
| `interrupt(payload)` - pause and ask | Examples 1, 2, 4, 5 |
| `result["__interrupt__"]` - the question, handed back | Examples 1, 2, 4 |
| `Command(resume=value)` - the answer | every example |
| `graph.get_state(config).next` - where it stopped | Examples 1, 2, 3, 4 |
| `compile(interrupt_before=[...])` - a static breakpoint | Example 3 |
| `invoke(None, config)` - continue a static pause | Example 3 |
| The resume value as **data**, not a yes/no | Example 2 |
| A `guard` node separate from the node that acts | Example 4 |
| `ToolNode` behind an approval gate | Example 4 |
| The question itself, restored from SQLite | Example 5 |
| A pause that outlives the process | Example 5 |
| A pause adds no nodes and no edges | `graph_diagram.py` output |

**Prerequisite:** a checkpointer. `interrupt()` in a graph compiled without one does not raise - it returns a
question nobody can ever answer. Session 2 is not optional here.

## The five examples

### Example 1 - the primitive

```
  __start__ --> write --> approve --> __end__
```

`approve` calls `interrupt()` and the run stops there:

```
  invoke returned keys : ['topic', 'draft', 'approved', 'note', '__interrupt__']
  question             : Approve this draft?
  draft                : A short post about LangGraph.
  paused at            : ('approve',)

  No node after this ran. The process could exit here and nothing would be lost.
```

Answering it is one call on the same thread:

```
  result   : {'topic': 'LangGraph', 'draft': 'A short post about LangGraph.',
              'approved': True, 'note': 'approved'}
  paused at: (nothing left - the run finished)
```

**The gotcha that gets everybody.** The example keeps a `TRACE` list and prints it after the resume:

```
  after the first invoke, the node has run once:
    approve() started (a real email would be sent here)

  after the resume, the same node has run again from the top:
    approve() started (a real email would be sent here)
    approve() started (a real email would be sent here)
    approve() resumed with True
```

`interrupt()` does not suspend a function in the middle. On resume LangGraph calls the **whole node again** and
`interrupt()` returns the saved answer. Any side effect placed above it happens twice. Ask first, act second.

### Example 2 - the answer is data

```
  __start__ --> write --> review --> __end__
```

`review` sends out a structured request and accepts a structured reply. Same graph, three endings:

```
  approve
    decision : approve
    author   : agent
    final    : 'Marketing copy for: a course called FDE. Built with LangGraph.'

  edit
    decision : edit
    author   : human
    final    : 'Marketing copy for a course called FDE. Learn by building, not by reading slides.'

  reject
    decision : reject
    author   : agent
    final    : ''
```

`author` is in the state on purpose: when the human rewrites the text, the record says so. That field is your audit
trail. Approve and edit are the difference between a signature and a correction, and both are one `Command`.

### Example 3 - static breakpoints, and why they are not enough

The Session 2 order pipeline, unchanged, with a breakpoint added at `compile()` time:

```
  __start__ --> reserve_stock --> charge_card --> ship --> __end__
```

```
  reserve_stock  -> stock reserved
  steps done     : ['reserve_stock']
  paused at      : ('charge_card',)
  '__interrupt__' in the return value? False
```

Note what is **missing**: no question, no payload, no answer channel. The only signal is `next`. Continuing is
`invoke(None, config)` - no value is passed, because there is nowhere for a value to go:

```
  charge_card    -> payment taken
  ship           -> dispatched
  steps done     : ['reserve_stock', 'charge_card', 'ship']
```

And the limitation, which nobody mentions:

```
    - resume it           -> invoke(None, config)      (yes)
    - never resume it     -> the thread sits paused forever ("no" by neglect)
```

That is fine for a debugger pause and wrong for a payment approval. It cannot record *why* it stopped, *who* looked at
it, or *what* they decided. **If a human must decide, use `interrupt()`.**

### Example 4 - approving a tool call

This is the pattern people actually ship:

```
  __start__ --> propose --> guard --(approved)--> tools --> __end__
                              |
                              +----(rejected)--> cancel --> __end__
```

`propose` stands in for a model and asks to run `delete_records`. The graph stops before anything is deleted:

```
    human: clean up the audit log
    agent: wants to call delete_records(table='audit_log', older_than_days=90)

  paused at   : ('guard',)
  tools run   : 0
```

Approve:

```
    human: clean up the audit log
    agent: wants to call delete_records(table='audit_log', older_than_days=90)
    tool: deleted rows older than 90 days from 'audit_log'

  tools run   : 1
```

Reject, on a fresh thread:

```
    agent: Cancelled - nothing was deleted.

  tools run   : 1  <- still 1, from the approved thread
```

**The node boundary is the lesson.** `guard` only asks, so asking twice costs nothing. `tools` only acts, so it runs
exactly once and only after a `True` arrived. That is the fix for Example 1's double-execution bug, made structural.

### Example 5 - the approval outlives the process

Example 4's graph, imported unchanged, with `SqliteSaver` instead of `MemorySaver`:

```
$ python example5_durable_approval.py
Process 1 - propose, pause, exit
  paused at : ('guard',)
  question  : approve tool call

  This process is about to exit. The question is now a row in .data/approvals.db.
```

The process ends. A different process, later, reads the queue:

```
$ python example5_durable_approval.py --approve
Process 2 - a pending approval found in the database
  paused at : ('guard',)
  question recovered from the database:
    {
      "action": "approve tool call",
      "tool": "delete_records",
      "args": { "table": "audit_log", "older_than_days": 90 },
      ...
    }

  resuming with Command(resume=True) ...
  tool: deleted rows older than 90 days from 'audit_log'
```

The question is recovered from the checkpoint, not from memory: it lives on the pending task
(`snapshot.tasks[0].interrupts[0].value`). That is what makes a real approval queue possible - the approver does not
need to be the process that asked, or even the same day.

## Project structure

```
example1_interrupt.py        The primitive: interrupt(), __interrupt__, Command(resume=), and the re-run trap.
example2_edit.py             The resume value is data: approve, edit or reject the same draft.
example3_breakpoint.py       Static interrupt_before / interrupt_after on Session 2's order pipeline.
example4_tool_approval.py    A guard node between the proposal and the tool. Approve or cancel.
example5_durable_approval.py Example 4's graph on SqliteSaver - approve it in a separate process.
graph_diagram.py             Prints the Mermaid source for every graph (--out writes .md files).
llm.py                       Not called - where Example 4's `propose` node plugs a real model in.
conftest.py                  Makes the project root importable for the tests.
tests/test_hitl.py           11 offline pytest tests - no API key needed.
docs/                        Diagrams: generated Mermaid plus the hand-drawn walkthrough.
```

## Setup

Python 3.10+ (3.12 recommended).

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
python -m pip install -r requirements.txt
```

> Use `python -m pip`, not bare `pip`. A globally installed `pip` can point at a different interpreter than your
> `python`, and then the packages land in the wrong place.

`langchain-core` is a direct dependency here (Example 4 imports `messages` and `tools` from it), so it is declared in
`requirements.txt` rather than relied on as a transitive one.

## Run

```bash
python example1_interrupt.py
python example2_edit.py
python example3_breakpoint.py
python example4_tool_approval.py

python example5_durable_approval.py --reset      # start clean
python example5_durable_approval.py              # process 1: pauses and exits
python example5_durable_approval.py --approve    # process 2: approves and runs the tool

python graph_diagram.py             # add --out docs to write one .md file per graph
python -m pytest -q                 # 11 offline tests
```

## Teaching flow (50 minutes)

| Time | Activity |
|---|---|
| 0:00-0:05 | Session 2 recap: a crashed graph resumes with `invoke(None, config)`. Now: do it on purpose |
| 0:05-0:10 | The pink-slip analogy. Question out, answer back, same file |
| 0:10-0:20 | Example 1 live. Point at `__interrupt__`, then `next`, then run the resume |
| 0:20-0:30 | Example 1's `TRACE`. Ask the room: *which line would you move?* Land on: ask first, act second |
| 0:30-0:35 | Example 2. Three threads, one question. `author` is the audit trail |
| 0:35-0:40 | Example 3. The same pipeline that crashed in Session 2, now paused on purpose. Then the limitation |
| 0:40-0:50 | Example 4, then Example 5 across two processes. The approval outlives the process |

If you are short on time, Example 5 can be a demo rather than a walkthrough - it is 40 lines and mostly printing.

## Preparation checklist

- [ ] Run Example 1. Confirm `TRACE` ends with **three** entries, two of them "started".
- [ ] Run Example 2. One sentence: *what is the difference between approve and edit?*
      **Approve accepts the agent's text; edit replaces it. Both are one `Command`.**
- [ ] Run Example 3. One sentence: *why is there no `__interrupt__` in the result?*
      **A static breakpoint has no payload - it is a position, not a question.**
- [ ] Run Example 4. Confirm `tools run : 0` before the resume and `1` after.
- [ ] Run Example 5 in two terminals. Confirm the question is printed by the second process.
- [ ] Draw the four checkpoints of Example 1 on the board and mark which one the pause lives in.
      **The third one - `next: ('approve',)`. The pause is not a new checkpoint.**

### Questions to be ready for

1. **Where does the answer go?**
   It becomes the return value of `interrupt()`. The node then runs to completion as usual, on its second execution.
2. **Does the node re-run from the beginning?**
   Yes, the whole function. `interrupt()` returns the stored answer instead of pausing. Anything with a side effect
   above it happens twice.
3. **So where do I put the side effect?**
   In a separate node that runs after the answer is known. `guard` asks, `tools` acts.
4. **Does `interrupt()` need a checkpointer?**
   To pause, no - it will happily hand you a question. To *resume*, yes, absolutely. Without one there is no thread
   and the run is dead.
5. **What is the difference from Session 2's crash-and-resume?**
   Nothing mechanically: both are a checkpoint with a non-empty `next`. The difference is intent. A crash is an
   accident; an `interrupt()` is a design decision with a question attached.
6. **Can I pause in the middle of a node?**
   No. You pause at a point in a node, and on resume the node starts over. Design nodes so the part before the
   interrupt is cheap and repeatable.
7. **`interrupt_before` or `interrupt()`?**
   `interrupt_before` if a human only needs to look. `interrupt()` if a human needs to decide, because only it has a
   return channel.
8. **Can two humans answer two questions in one node?**
   Yes - two `interrupt()` calls, two resumes. The earlier answer is replayed on each restart, which is correct but
   worth knowing before you try it.

## Common mistakes

| Symptom | Likely cause | Fix |
|---|---|---|
| `__interrupt__` in the result but nothing can resume | No checkpointer | `compile(checkpointer=...)` and pass a `thread_id` |
| The email went out twice | Side effect placed above `interrupt()` | Move it into a node that runs after the answer |
| `Command(resume=...)` does nothing | The thread is not paused | Check `get_state(config).next` first |
| `KeyError: '__interrupt__'` | Static breakpoint, or the graph already finished | Read `next` instead - it is the universal signal |
| Resume value arrives as `None` | You called `invoke(None, config)` | Use `Command(resume=value)` for a dynamic interrupt |
| The paused run cannot be found | Different `thread_id` or a different database file | Same thread, same checkpointer |
| A node runs again after resuming | That is the design | Accept it, or split ask from act |
| The tool ran before anyone approved | The approval is after the tool, not before it | Put the `guard` node in front of `tools` |
| An order is stuck forever | Static breakpoint with no answer channel | Use `interrupt()` and branch on the answer |

**Good habits:** ask in one node and act in another, keep the interrupt payload JSON-shaped, and resume with the same
`thread_id` you paused with.
**Habits to avoid:** `interrupt()` without a checkpointer, and burying `interrupt()` deep inside a node that also
writes things.

## Notes and differences

- **A pause is not a checkpoint of its own.** The last checkpoint says `next: ('approve',)` and keeps saying it until
  the answer arrives. That is why resuming re-runs the node.
- **The question is checkpointed.** It lives on `snapshot.tasks[*].interrupts[*].value`, not in `values`. Example 5
  reads it back from SQLite.
- **The resume value is JSON, not a callback.** Strings, dicts, booleans - it is serialised with the checkpoint, so it
  has to survive a round trip.
- **`interrupt_before` adds no node.** A breakpoint is a runtime position, so the Mermaid output is identical before
  and after; `graph_diagram.py` proves it.
- **`Command(resume=...)` on a finished thread is silently ignored.** No error, no effect. Check `next` if a resume
  seems to do nothing.
- **One graph object serves many paused threads.** The pause is in the checkpoint, not in the graph.

## Where the model goes

Nothing in this repo calls a model. Human-in-the-loop is about *where a graph pauses*, not about what a node computes,
and keeping the nodes deterministic is what makes every output above reproducible in class.

Example 4 is shaped like a real agent, and its `propose` node is the one place a model belongs:

```python
from llm import get_llm
from langchain_core.messages import SystemMessage

def propose(state):
    reply = get_llm().invoke([SystemMessage("You are a careful ops assistant."), *state["messages"]])
    return {"messages": [reply]}      # reply.tool_calls is what the guard asks about
```

The `guard`, the `interrupt`, the `ToolNode` and the approval flow are unchanged. That is the point worth making: the
model decides *what to ask for*; the human still decides *whether it happens*.

## What's next

Session 4: long-term memory with a `BaseStore` - facts that outlive a thread, not just a run. Checkpoints are
per-thread (this conversation); a store is per-user (this person, forever).

The nice detail for that session: Session 3's approval queue is keyed by thread, so it already answers "what is
pending for this case?". A store answers the harder question: "what do we know about this customer?"
