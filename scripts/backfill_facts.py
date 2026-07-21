"""Backfill atomic facts for journal entries saved before facts existed.

Reads every entry, skips the ones that already have facts (so it's safe to
re-run), and runs the fact extraction on the rest. This spends LLM calls — one
per entry — so it prints how many entries it's about to process first.

    docker compose up -d          # needs Postgres + the vector extension
    uv run python -m scripts.backfill_facts
"""
from sqlalchemy import select

from app.core import db
from app.models import Entry
from app.services import facts


def main() -> None:
    with db.get_session() as s:
        all_entries = list(s.scalars(select(Entry).order_by(Entry.id)))

    # Group already-processed entry ids per user so we skip them.
    done_by_user: dict[str, set[int]] = {}
    todo = []
    for e in all_entries:
        done = done_by_user.get(e.user_id)
        if done is None:
            done = facts.existing_fact_entry_ids(e.user_id)
            done_by_user[e.user_id] = done
        if e.id not in done:
            todo.append(e)

    print(f"{len(todo)} ent(r)ies to process (of {len(all_entries)} total).")
    for i, e in enumerate(todo, 1):
        try:
            ids = facts.extract_and_save(e.id, e.transcript, e.ai_reply, e.user_id)
            print(f"[{i}/{len(todo)}] entry {e.id}: {len(ids)} facts")
        except Exception as exc:  # keep going; one bad entry shouldn't stop it
            print(f"[{i}/{len(todo)}] entry {e.id}: FAILED — {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
