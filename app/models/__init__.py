"""Database models.

Importing every model here matters: `Base.metadata` only knows about tables
whose module has been imported, so `create_all` would silently skip any model
nobody imported yet. It also lets callers write `from app.models import Entry`
without caring which file it lives in.
"""
from app.models.base import Base
from app.models.entry import Entry
from app.models.fact import Fact
from app.models.mantra import Mantra
from app.models.profile import Profile

# Marks these as deliberate re-exports, so the linter doesn't read them as
# unused imports.
__all__ = ["Base", "Entry", "Fact", "Mantra", "Profile"]
