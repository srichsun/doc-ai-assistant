"""FastAPI entrypoint for the document Q&A assistant."""
from fastapi import FastAPI
from pydantic import BaseModel

from app import llm

app = FastAPI(title="Doc AI Assistant")


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    answer = llm.generate(req.question)
    return ChatResponse(answer=answer)
