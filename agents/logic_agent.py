"""
Logic Agent — finds bugs, edge cases, and logical errors.
Thinks like: "Will this code break at runtime?"
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from agents.base_agent import run_agent
from db.connection import get_session
from db.models import ReviewComment

SYSTEM_PROMPT = """You are a senior software engineer specializing in code logic review.
Your job is to find:
- Runtime bugs (null pointer, index out of bounds, type errors)
- Off-by-one errors
- Missing edge cases (empty input, None values, negative numbers)
- Wrong conditionals or flipped logic
- Unreachable code or infinite loops
- Missing error handling

Be precise. Only flag real issues — not style preferences.
Always respond in the exact format requested."""


def run_logic_agent(chunks: List[Dict], review_run_id: int) -> List[Dict]:
    """Review all chunks for logic issues, save to DB, return comments."""
    all_comments = []

    for chunk in chunks:
        print(f"  [Logic Agent] Reviewing {chunk['file_path']}...")
        comment = run_agent(
            agent_name="logic",
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

    print(f"  [Logic Agent] Found {len([c for c in all_comments if c['comment'] != 'No issues found'])} issues")
    return all_comments