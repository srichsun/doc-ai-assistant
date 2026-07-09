"""FastAPI entrypoint for the document Q&A assistant."""
from fastapi import FastAPI
from pydantic import BaseModel

from app import llm, rag

app = FastAPI(title="Doc AI Assistant")


class ChatRequest(BaseModel):
    question: str


class Source(BaseModel):
    source: str
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


def _dedupe_sources(hits: list[dict]) -> list[Source]:
    """One Source per (file, page), preserving retrieval order."""
    seen, sources = set(), []
    for h in hits:
        key = (h["source"], h.get("page"))
        if key not in seen:
            seen.add(key)
            sources.append(Source(source=h["source"], page=h.get("page")))
    return sources


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search")
def search(q: str):
    """Return the most relevant chunks for a query (retrieval sanity check)."""
    return {"query": q, "hits": rag.retrieve(q)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    hits = rag.retrieve(req.question)
    if not hits:
        return ChatResponse(
            answer="I don't have any documents to answer that from.", sources=[]
        )
    prompt = rag.build_prompt(req.question, hits)
    answer = llm.generate(prompt, system=rag.SYSTEM_PROMPT)
    return ChatResponse(answer=answer, sources=_dedupe_sources(hits))
