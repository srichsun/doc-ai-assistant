"""Request shapes for writing the journal.

Kept separate from the database models: what a caller may send is not the same
thing as what we store.
"""
from pydantic import BaseModel, Field, field_validator


class EntryWrite(BaseModel):
    """Today's journal entry, as the browser sends it."""

    content: str
    # Self-rated 1-10, filled in after writing. Ten steps, not a hundred: nobody
    # can tell their own 67 from their 71, and a scale finer than the judgement
    # behind it just makes the trend line look precise while meaning less. The
    # UI shows it as a percentage.
    energy: int | None = Field(default=None, ge=1, le=10)

    @field_validator("content")
    @classmethod
    def _must_write_something(cls, v: str) -> str:
        """Reject a blank day rather than storing an empty entry.

        An empty entry would spend one of the day's edits, show up as a written
        day on the chart, and give the analysis nothing to read.
        """
        v = v.strip()
        if not v:
            raise ValueError("write something first")
        return v
