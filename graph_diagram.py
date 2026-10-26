"""
graph_diagram.py - print the Mermaid source for every graph in this project.

Run:  python graph_diagram.py             # print to the terminal
      python graph_diagram.py --out docs  # also write one .md file per graph into ./docs

Paste the Mermaid source into https://mermaid.live to get a picture, or into any Markdown file that renders Mermaid.

Note: a breakpoint does not change the SHAPE of a graph either. Neither interrupt() nor interrupt_before= adds a node
or an edge - pausing is a runtime event. The shape that matters in this repo is the one in Example 4: the guard node
sitting between the proposal and the tool, with two outgoing branches.
"""
import argparse
from pathlib import Path

from example1_interrupt import build_graph as build_example1
from example2_edit import build_graph as build_example2
from example3_breakpoint import build_graph as build_example3
from example4_tool_approval import build_graph as build_example4


GRAPHS = [
    ("example1-interrupt", "Example 1 - ask, then resume", build_example1),
    ("example2-edit", "Example 2 - approve, edit or reject", build_example2),
    ("example3-order", "Example 3 - the order pipeline with a static breakpoint", build_example3),
    ("example4-tool-approval", "Example 4 - a guard between the proposal and the tool", build_example4),
]


def mermaid_for(builder) -> str:
    """Return the Mermaid source for a compiled graph."""
    return builder().get_graph().draw_mermaid()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="DIR", help="also write one .md file per graph into this directory")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for slug, title, builder in GRAPHS:
        source = mermaid_for(builder)

        print("=" * 72)
        print(title)
        print("=" * 72)
        print(source)
        print()

        if out_dir:
            path = out_dir / f"{slug}.md"
            path.write_text(f"# {title}\n\n```mermaid\n{source}\n```\n", encoding="utf-8")
            print(f"wrote {path}\n")


if __name__ == "__main__":
    main()
