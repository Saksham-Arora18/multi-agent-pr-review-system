import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from db.connection import get_session
from db.models import PullRequest, ReviewRun, PRChunk

# Load embedding model once at module level (expensive to reload each time)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
embedder = SentenceTransformer(EMBEDDING_MODEL)


# -------------------------------------------------------------------
# 1. CHUNKING — break diff into small reviewable pieces
# -------------------------------------------------------------------

def parse_diff_into_chunks(diff_text: str, max_lines: int = 30) -> List[Dict]:
    """
    Split a raw git diff into per-file chunks.
    Each chunk = one file's diff, capped at max_lines lines.

    Why chunk? LLMs have context limits. A PR with 20 files changed
    can't be reviewed in one shot — we chunk so each agent call
    gets focused, relevant context instead of noise.
    """
    chunks = []
    current_file = None
    current_lines = []

    for line in diff_text.splitlines():
        # New file in diff — save previous, start fresh
        if line.startswith("diff --git"):
            if current_file and current_lines:
                chunks.append({
                    "file_path": current_file,
                    "content": "\n".join(current_lines),
                    "chunk_type": "diff"
                })
            # Extract file path from "diff --git a/path b/path"
            parts = line.split(" ")
            current_file = parts[-1].replace("b/", "", 1) if len(parts) >= 4 else "unknown"
            current_lines = [line]

        else:
            current_lines.append(line)

            # If chunk is getting too long, split it
            if len(current_lines) >= max_lines:
                chunks.append({
                    "file_path": current_file,
                    "content": "\n".join(current_lines),
                    "chunk_type": "diff"
                })
                current_lines = []  # reset for next chunk of same file

    # Don't forget the last file
    if current_file and current_lines:
        chunks.append({
            "file_path": current_file,
            "content": "\n".join(current_lines),
            "chunk_type": "diff"
        })

    return chunks


# -------------------------------------------------------------------
# 2. EMBEDDING — convert text chunks to vectors
# -------------------------------------------------------------------

def embed_chunks(chunks: List[Dict]) -> List[Dict]:
    """
    Add 'embedding' key to each chunk dict.
    Uses BAAI/bge-small-en-v1.5 — 384 dimensions, fast, good quality.
    """
    texts = [chunk["content"] for chunk in chunks]
    embeddings = embedder.encode(texts, normalize_embeddings=True)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding.tolist()  # numpy → python list for DB storage

    return chunks


# -------------------------------------------------------------------
# 3. STORE — save chunks to DB
# -------------------------------------------------------------------

def store_chunks(pr_id: int, chunks: List[Dict]) -> None:
    """
    Insert embedded chunks into pr_chunks table.
    Old chunks for this PR are deleted first to avoid duplicates
    on re-review (when new commits are pushed).
    """
    with get_session() as session:
        # Clean old chunks for this PR before inserting fresh ones
        session.query(PRChunk).filter_by(pr_id=pr_id).delete()

        for chunk in chunks:
            db_chunk = PRChunk(
                pr_id=pr_id,
                file_path=chunk["file_path"],
                chunk_type=chunk["chunk_type"],
                content=chunk["content"],
                embedding=chunk["embedding"]
            )
            session.add(db_chunk)

    print(f"Stored {len(chunks)} chunks for PR id={pr_id}")


# -------------------------------------------------------------------
# 4. RETRIEVE — find similar past chunks (RAG part)
# -------------------------------------------------------------------

def retrieve_similar_chunks(query_text: str, pr_id: int, top_k: int = 5) -> List[Dict]:
    """
    Given a query (e.g. a piece of new code), find the most similar
    chunks from PAST PRs using cosine similarity on embeddings.

    This is the RAG step — gives agents historical context:
    "Has similar code caused bugs before? What was reviewed then?"

    Excludes chunks from the current PR (pr_id) so we don't
    retrieve the very thing we're reviewing.
    """
    query_embedding = embedder.encode([query_text], normalize_embeddings=True)[0].tolist()

    with get_session() as session:
        # pgvector cosine similarity search using <=> operator
        # Lower <=> value = more similar (cosine distance, not similarity)
        results = session.execute(
            text("""
                SELECT file_path, content, chunk_type,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM pr_chunks
                WHERE pr_id != :pr_id
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            """),
            {
                "embedding": str(query_embedding),
                "pr_id": pr_id,
                "top_k": top_k
            }
        ).fetchall()

    return [
        {
            "file_path": row.file_path,
            "content": row.content,
            "chunk_type": row.chunk_type,
            "similarity": round(row.similarity, 4)
        }
        for row in results
    ]


# -------------------------------------------------------------------
# 5. MAIN ENTRY POINT — called by orchestrator
# -------------------------------------------------------------------

def run_retrieval_agent(pr_id: int, diff_text: str) -> Dict:
    """
    Full retrieval pipeline for one PR:
    parse → embed → store → return chunks for downstream agents.

    Returns a dict the orchestrator passes to specialist agents.
    """
    print(f"\n[Retrieval Agent] Processing PR id={pr_id}")

    # Step 1: Parse diff into chunks
    chunks = parse_diff_into_chunks(diff_text)
    print(f"  Parsed {len(chunks)} chunks from diff")

    # Step 2: Embed chunks
    chunks = embed_chunks(chunks)
    print(f"  Embedded {len(chunks)} chunks")

    # Step 3: Store in DB
    store_chunks(pr_id, chunks)

    # Step 4: For each chunk, find similar past context
    # (used by specialist agents to enrich their review)
    enriched_chunks = []
    for chunk in chunks:
        similar = retrieve_similar_chunks(chunk["content"], pr_id, top_k=3)
        enriched_chunks.append({
            **chunk,
            "similar_past_chunks": similar
        })

    print(f"  Retrieval complete — {len(enriched_chunks)} enriched chunks ready")

    return {
        "pr_id": pr_id,
        "chunks": enriched_chunks,
        "total_chunks": len(enriched_chunks)
    }