"""
Test Agent — checks test coverage and quality.
Thinks like: "Can I trust this code won't silently break?"
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from agents.base_agent import run_agent
from db.connection import get_session
from db.models import ReviewComment

SYSTEM_PROMPT = """You are a senior engineer focused on testing and reliability.
Your job is to find:
- New functions added without corresponding test cases
- Missing edge case tests (empty input, None, boundary values)
- Tests that only test the happy path, ignoring failures
- Missing error/exception handling tests
- Functions with complex logic but no unit tests

If you see only non-testable code (config, constants, simple getters),
say no issues. Only flag real gaps in test coverage.
Always respond in the exact format requested."""


def run_test_agent(chunks: List[Dict], review_run_id: int) -> List[Dict]:
    """Review all chunks for test coverage gaps, save to DB, return comments."""
    all_comments = []

    for chunk in chunks:
        print(f"  [Test Agent] Reviewing {chunk['file_path']}...")
        comment = run_agent(
            agent_name="test",
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

    print(f"  [Test Agent] Found {len([c for c in all_comments if c['comment'] != 'No issues found'])} issues")
    return all_comments