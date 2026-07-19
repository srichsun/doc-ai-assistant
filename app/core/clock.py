"""The app's idea of "today".

A journal day should end at midnight where the person lives, not at UTC
midnight (which is 8am in Taiwan — mid-morning, halfway through a thought).
Both the conversation the coach remembers and the entries screen ask this
module what "today" means, so the two can never disagree.
"""
from datetime import date, datetime, time, timedelta, timezone

# Taiwan time. A fixed offset is enough — Taiwan has no daylight saving.
TZ = timezone(timedelta(hours=8))


def today() -> date:
    """The current journal day."""
    return datetime.now(TZ).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The first and last instant of a journal day.

    Timezone-aware, so comparing them against the UTC timestamps stored in the
    database lines up correctly.
    """
    return (
        datetime.combine(day, time.min, tzinfo=TZ),
        datetime.combine(day, time.max, tzinfo=TZ),
    )
