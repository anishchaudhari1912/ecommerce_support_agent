"""
Document Ingestion Pipeline
============================
Ingests policy markdown documents, chunks them with overlap,
embeds them using sentence-transformers, and stores in ChromaDB.

Chunking Strategy:
- Chunk size: 600 tokens (~450 words) — large enough to preserve context
  within a policy section, small enough to keep retrieval precise.
- Overlap: 100 tokens — prevents losing information at chunk boundaries
  (especially for numbered lists that span chunk edges).
- Split preference: paragraph > sentence > token — preserves semantic units.
- Metadata: every chunk carries doc_id, section title, chunk_index,
  source URL so the retriever can emit proper citations.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
POLICIES_DIR = Path(__file__).parent.parent / "data" / "policies"
CHROMA_DIR   = Path(__file__).parent.parent / "data" / "chroma_db"
COLLECTION_NAME = "shopcore_policies"

CHUNK_SIZE_CHARS   = 1800   # ~600 tokens (3 chars ≈ 1 token)
CHUNK_OVERLAP_CHARS = 300   # ~100 tokens
EMBEDDING_MODEL    = "all-MiniLM-L6-v2"   # fast, accurate, 384-dim


# ──────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    chunk_id:   str
    doc_id:     str
    doc_title:  str
    source_url: str
    section:    str        # e.g. "Section 3: Non-Returnable / Final Sale Items"
    subsection: str        # e.g. "3.1 Categories Ineligible for Return"
    text:       str
    chunk_index: int


# ──────────────────────────────────────────────────────────────
# Markdown parser
# ──────────────────────────────────────────────────────────────
def parse_markdown_document(filepath: Path) -> Dict[str, Any]:
    """Extract metadata and section-aware content from a policy .md file."""
    raw = filepath.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # Pull header metadata (first ~6 lines)
    doc_id    = _extract_meta(lines, "Document ID:")
    source    = _extract_meta(lines, "Source:")
    title_line = next((l for l in lines if l.startswith("# ")), "")
    title     = title_line.lstrip("# ").strip()

    return {
        "doc_id":     doc_id or filepath.stem,
        "doc_title":  title,
        "source_url": source or "",
        "raw":        raw,
        "filepath":   str(filepath),
    }


def _extract_meta(lines: List[str], key: str) -> Optional[str]:
    for l in lines:
        if key in l:
            return l.split(key, 1)[-1].strip()
    return None


# ──────────────────────────────────────────────────────────────
# Section-aware chunker
# ──────────────────────────────────────────────────────────────
_H2 = re.compile(r"^## (.+)$")
_H3 = re.compile(r"^### (.+)$")


def chunk_document(meta: Dict[str, Any]) -> List[Chunk]:
    """Split a policy document into overlapping, section-labelled chunks."""
    raw = meta["raw"]
    chunks: List[Chunk] = []
    current_section    = ""
    current_subsection = ""
    buffer             = ""
    chunk_index        = 0

    def flush(section: str, subsection: str, text: str, idx: int) -> Optional[Chunk]:
        text = text.strip()
        if len(text) < 60:   # skip tiny fragments
            return None
        uid = hashlib.md5(f"{meta['doc_id']}-{idx}-{text[:40]}".encode()).hexdigest()[:12]
        return Chunk(
            chunk_id    = f"{meta['doc_id']}-{idx:03d}-{uid}",
            doc_id      = meta["doc_id"],
            doc_title   = meta["doc_title"],
            source_url  = meta["source_url"],
            section     = section,
            subsection  = subsection,
            text        = text,
            chunk_index = idx,
        )

    def maybe_split_and_flush():
        nonlocal buffer, chunk_index
        # Flush when buffer exceeds CHUNK_SIZE_CHARS
        while len(buffer) > CHUNK_SIZE_CHARS:
            split_at = buffer.rfind("\n\n", 0, CHUNK_SIZE_CHARS)
            if split_at == -1:
                split_at = CHUNK_SIZE_CHARS
            piece  = buffer[:split_at]
            c = flush(current_section, current_subsection, piece, chunk_index)
            if c:
                chunks.append(c)
                chunk_index += 1
            # Keep overlap
            overlap_start = max(0, split_at - CHUNK_OVERLAP_CHARS)
            buffer = buffer[overlap_start:]

    for line in raw.splitlines():
        m2 = _H2.match(line)
        m3 = _H3.match(line)

        if m2:
            # Flush buffer before new section
            c = flush(current_section, current_subsection, buffer, chunk_index)
            if c:
                chunks.append(c)
                chunk_index += 1
            buffer = ""
            current_section    = m2.group(1).strip()
            current_subsection = ""
        elif m3:
            c = flush(current_section, current_subsection, buffer, chunk_index)
            if c:
                chunks.append(c)
                chunk_index += 1
            # keep overlap context into next subsection
            overlap = buffer[-CHUNK_OVERLAP_CHARS:].strip() if buffer else ""
            buffer = overlap + "\n" if overlap else ""
            current_subsection = m3.group(1).strip()
        else:
            buffer += line + "\n"
            maybe_split_and_flush()

    # Final flush
    c = flush(current_section, current_subsection, buffer, chunk_index)
    if c:
        chunks.append(c)

    return chunks


# ──────────────────────────────────────────────────────────────
# Embedding + ChromaDB storage
# ──────────────────────────────────────────────────────────────
def build_index(policies_dir: Path = POLICIES_DIR,
                chroma_dir:   Path = CHROMA_DIR,
                reset:        bool = False) -> chromadb.Collection:
    """Ingest all policy documents and build the vector index."""
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=Settings(anonymized_telemetry=False),
    )

    if reset and COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Check if already indexed
    existing_ids = set(collection.get()["ids"])
    if existing_ids and not reset:
        print(f"[ingestion] Collection already has {len(existing_ids)} chunks. Skipping re-index.")
        return collection

    print(f"[ingestion] Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    all_chunks: List[Chunk] = []
    md_files = sorted(policies_dir.glob("*.md"))
    print(f"[ingestion] Found {len(md_files)} policy documents")

    for fp in md_files:
        meta   = parse_markdown_document(fp)
        chunks = chunk_document(meta)
        all_chunks.extend(chunks)
        print(f"  → {fp.name}: {len(chunks)} chunks")

    print(f"[ingestion] Total chunks: {len(all_chunks)}")

    # Batch-embed and upsert
    BATCH = 64
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i : i + BATCH]
        texts = [c.text for c in batch]
        ids   = [c.chunk_id for c in batch]
        metas = [
            {
                "doc_id":      c.doc_id,
                "doc_title":   c.doc_title,
                "source_url":  c.source_url,
                "section":     c.section,
                "subsection":  c.subsection,
                "chunk_index": c.chunk_index,
            }
            for c in batch
        ]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
        print(f"  [upsert] batch {i//BATCH + 1}/{-(-len(all_chunks)//BATCH)}")

    print(f"[ingestion] Done. {len(all_chunks)} chunks indexed in ChromaDB at {chroma_dir}")
    return collection


def get_collection(chroma_dir: Path = CHROMA_DIR) -> chromadb.Collection:
    """Return existing ChromaDB collection (must call build_index first)."""
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_collection(COLLECTION_NAME)


def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


# ──────────────────────────────────────────────────────────────
# Retriever
# ──────────────────────────────────────────────────────────────
def retrieve(
    query:      str,
    model:      SentenceTransformer,
    collection: chromadb.Collection,
    top_k:      int = 5,
    doc_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve top-k relevant chunks for a query.

    Args:
        query:      The search query string.
        model:      SentenceTransformer for embedding.
        collection: ChromaDB collection.
        top_k:      Number of results to return.
        doc_filter: If set, only return chunks from these doc_ids.

    Returns:
        List of dicts with keys: chunk_id, doc_id, doc_title, source_url,
        section, subsection, text, score (cosine similarity).
    """
    query_emb = model.encode([query]).tolist()

    where = None
    if doc_filter:
        where = {"doc_id": {"$in": doc_filter}}

    results = collection.query(
        query_embeddings=query_emb,
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    ids_row = results["ids"][0]
    for i, (doc, meta, dist) in enumerate(
        zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ):
        hits.append({
            "chunk_id":   ids_row[i],
            "doc_id":     meta["doc_id"],
            "doc_title":  meta["doc_title"],
            "source_url": meta["source_url"],
            "section":    meta["section"],
            "subsection": meta["subsection"],
            "text":       doc,
            "score":      round(1 - dist, 4),   # cosine similarity
        })

    return hits


# ──────────────────────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build ShopCore policy index")
    parser.add_argument("--reset", action="store_true", help="Delete and rebuild index")
    args = parser.parse_args()
    build_index(reset=args.reset)