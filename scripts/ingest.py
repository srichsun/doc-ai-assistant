"""CLI: ingest the data/ directory into the vector store.

Usage: uv run python -m scripts.ingest [data_dir]
"""
import sys

from app import rag


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    counts = rag.ingest_dir(data_dir)
    if not counts:
        print(f"No supported files found in {data_dir}/")
        return
    total = sum(counts.values())
    for name, n in counts.items():
        print(f"  {name}: {n} chunks")
    print(f"Ingested {total} chunks from {len(counts)} file(s).")


if __name__ == "__main__":
    main()
