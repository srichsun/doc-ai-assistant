"""Request/response shapes for the coach and voice endpoints.

These are the API contract — what the browser sends and what it gets back.
FastAPI validates incoming JSON against them and documents them at /docs.
Kept separate from the database models: what a caller may send is not the same
thing as what we store.
"""
from pydantic import BaseModel


class TalkRequest(BaseModel):
    question: str


class TalkResponse(BaseModel):
    answer: str


class SpeakRequest(BaseModel):
    text: str
