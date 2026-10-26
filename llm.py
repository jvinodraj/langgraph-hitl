"""
llm.py - one place that knows how to build a chat model.

Every example in this repo runs without an API key. Human-in-the-loop is about *where a graph pauses*, not about
what a node computes, so the nodes here are deterministic on purpose - the same question, the same draft, the same
tool call, every single run. That is what makes an approval flow testable.

This file exists because Example 4 is shaped like a real agent. Its `propose` node is the one place a model belongs:

    from llm import get_llm
    from langchain_core.messages import SystemMessage

    def propose(state):
        reply = get_llm().invoke([SystemMessage(...), *state["messages"]])
        return {"messages": [reply]}      # reply.tool_calls carries the request the guard will ask about

Swap that in and nothing else changes: the guard, the interrupt, the tool node and the whole approval flow are
untouched. The model decides what to ask for; the human still decides whether it happens.

We talk to OpenRouter (an OpenAI-compatible gateway) through LangChain's ChatOpenAI class, so switching from GPT to
Claude to Gemini to Llama is just a different model-name string - nothing else in the app changes.
"""
import os

from dotenv import load_dotenv

try:  # importing this module must still work if langchain-openai is not installed
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None

load_dotenv()  # reads OPENROUTER_API_KEY from a local .env file (ignored by git)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def has_api_key() -> bool:
    """True when OPENROUTER_API_KEY is available."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def get_llm(temperature: float = 0.3):
    """Return a ChatOpenAI pointed at OpenRouter, always using DEFAULT_MODEL."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set (see .env.example).")
    if ChatOpenAI is None:  # pragma: no cover
        raise ImportError("langchain-openai is not installed. Run: python -m pip install -r requirements.txt")
    return ChatOpenAI(
        model=DEFAULT_MODEL,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
    )
