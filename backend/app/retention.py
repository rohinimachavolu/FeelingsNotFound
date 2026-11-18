"""End-of-course data deletion."""
from __future__ import annotations

from sqlalchemy import delete, func, select, text

from .db import get_engine, session_scope
from .models import Flag, Message, PageEvent, Participant, Response

CONFIRM_PHRASE = "DELETE"


def delete_all_data() -> dict:
    """Delete every participant (human and persona) and all their responses, messages, flags and timings."""
    with session_scope() as s:
        counts = {
            "participants": s.scalar(select(func.count()).select_from(Participant)),
            "responses": s.scalar(select(func.count()).select_from(Response)),
            "messages": s.scalar(select(func.count()).select_from(Message)),
            "flags": s.scalar(select(func.count()).select_from(Flag)),
            "page_events": s.scalar(select(func.count()).select_from(PageEvent)),
        }
        for model in (Response, Message, Flag, PageEvent, Participant):
            s.execute(delete(model))
    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        # Rewrite the file so deleted rows don't linger in free pages or the WAL.
        with engine.connect() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            conn.execute(text("VACUUM"))
    return counts
