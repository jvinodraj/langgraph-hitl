"""
conftest.py - make the project root importable.

pytest adds the tests/ directory to sys.path, not the project root, so without this the tests could not do
`import example1_interrupt`.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
