"""Talking to the coach — the app's main endpoint."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.schemas.coach import TalkRequest, TalkResponse
from app.services import agent

router = APIRouter(tags=["coach"])


@router.post("/agent", response_model=TalkResponse)
def talk(req: TalkRequest, uid: CurrentUser):
    """Talk to the coach. The exchange is saved as a journal entry.

    Requires sign-in. The coach remembers by replaying today's journal
    entries for this user, so there is nothing to pass in but the question.
    """
    return agent.chat_and_log(req.question, user_id=uid)


@router.post("/agent/stream")
def talk_stream(req: TalkRequest, uid: CurrentUser):
    """Same as /agent, but streams the reply token by token (typewriter effect).
    The exchange is saved once streaming completes."""
    return StreamingResponse(
        agent.stream_and_log(req.question, user_id=uid),
        media_type="text/plain",
    )
