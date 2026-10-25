"""
Build the RAG index from rag/knowledge (seed notes) and rag/sources (your files).

    python -m rag.ingest            # keyword (BM25) index only, no model needed
    python -m rag.ingest --embed    # also embed with Ollama (run: ollama pull nomic-embed-text)
"""
from __future__ import annotations

import argparse

import config
from rag.store import KnowledgeBase
from tutor.llm import OllamaClient


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embed", action="store_true", help="also build dense embeddings via Ollama")
    ap.add_argument("--model", default=config.EMBED_MODEL, help="Ollama embedding model")
    args = ap.parse_args()
    client = OllamaClient() if args.embed else None
    if args.embed and not client.available():
        raise SystemExit("Ollama is not running. Start it (ollama serve) or run without --embed.")
    kb = KnowledgeBase()
    for line in kb.build(client=client, embed=args.embed, embed_model=args.model):
        print(" ", line)
    print("Retrieval mode:", kb.mode)


if __name__ == "__main__":
    main()
