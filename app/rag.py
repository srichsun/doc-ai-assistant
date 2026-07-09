"""Document ingestion: read files, split into chunks, store in Chroma."""
from pathlib import Path

from pypdf import PdfReader

from app import config, store


def _read_segments(path: Path) -> list[tuple[str, int | None]]:
    """Return (text, page) segments. PDFs are split per page; text files
    are a single segment with page=None."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return [(page.extract_text() or "", i + 1) for i, page in enumerate(reader.pages)]
    if suffix in (".md", ".txt"):
        return [(path.read_text(encoding="utf-8"), None)]
    raise ValueError(f"Unsupported file type: {path.name}")


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping character windows."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def ingest_file(path: Path) -> int:
    """Chunk a single file and add it to the vector store. Returns chunk count."""
    collection = store.get_collection()
    documents, metadatas, ids = [], [], []

    for text, page in _read_segments(path):
        for idx, chunk in enumerate(_chunk(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)):
            meta = {"source": path.name}
            if page is not None:
                meta["page"] = page
            documents.append(chunk)
            metadatas.append(meta)
            ids.append(f"{path.name}:{page}:{idx}")

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    return len(documents)


def ingest_dir(data_dir: str = "data") -> dict[str, int]:
    """Ingest every supported file in a directory. Returns {filename: chunks}."""
    counts = {}
    for path in sorted(Path(data_dir).iterdir()):
        if path.suffix.lower() in (".pdf", ".md", ".txt"):
            counts[path.name] = ingest_file(path)
    return counts
