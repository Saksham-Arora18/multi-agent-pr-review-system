"""
Style Agent — checks code style and conventions.
Thinks like: "Does this match how we write code here?"
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from agents.base_agent import run_agent
from db.connection import get_session
from db.models import ReviewComment

SYSTEM_PROMPT = """You are a senior engineer focused on code quality and maintainability.
Your job is to find:
- Poor naming (single letters, unclear variable names like 'x', 'tmp', 'data')
- Missing or inadequate docstrings/comments on complex functions
- Functions doing too many things (violates single responsibility)
- TODO/FIXME/HACK comments left in production code
- Dead code or commented-out code blocks
- Inconsistent code style within the file
- Magic numbers without explanation

Only flag things that genuinely hurt readability or maintainability.
Always respond in the exact format requested."""


def run_style_agent(chunks: List[Dict], review_run_id: int) -> List[Dict]:
    """Review all chunks for style issues, save to DB, return comments."""
    all_comments = []

    for chunk in chunks:
        print(f"  [Style Agent] Reviewing {chunk['file_path']}...")
        comment = run_agent(
            agent_name="style",
            system_prompt=SYSTEM_PROMPT,
            chunk=chunk,
            review_run_id=review_run_id
        )
        all_comments.append(comment)

    # Save to DB
    with get_session() as session:
        for c in all_comments:
            if c["comment"] != "No issues found":
                session.add(ReviewComment(**{k: v for k, v in c.items()}))

    print(f"  [Style Agent] Found {len([c for c in all_comments if c['comment'] != 'No issues found'])} issues")
    return all_comments