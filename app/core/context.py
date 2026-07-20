"""What the agent needs to know about the caller, for one run.

LangChain calls the dynamic prompt and the tools itself, so we can't hand them
the uid as a normal argument. `context=` is LangChain's own channel for exactly
that: pass it once on invoke, and both sides read it off `runtime.context`.
"""
from dataclasses import dataclass


@dataclass
class CoachContext:
    """The signed-in person, for the duration of one agent run."""

    user_id: str | None = None
