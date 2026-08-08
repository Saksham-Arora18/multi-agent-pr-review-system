"""
Security Agent — finds security vulnerabilities.
Thinks like: "Can this code be exploited?"
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from agents.base_agent import run_agent
from db.connection import get_session
from db.models import ReviewComment

SYSTEM_PROMPT = """You are a senior application security engineer.
Your job is to find:
- SQL injection vulnerabilities (f-strings in queries, string concatenation in SQL)
- Hardcoded secrets, API keys, passwords in code
- Weak cryptography (MD5, SHA1 for passwords — use bcrypt/argon2)
- Missing authentication or authorization checks
- Exposed sensitive data in logs or responses
- Command injection, path traversal vulnerabilities
- Insecure direct object references

Be precise and specific. Rate your confidence honestly.
Always respond in the exact format requested."""


def run_security_agent(chunks: List[Dict], review_run_id: int) -> List[Dict]:
    """Review all chunks for security issues, save to DB, return comments."""
    all_comments = []

    for chunk in chunks:
        print(f"  [Security Agent] Reviewing {chunk['file_path']}...")
        comment = run_agent(
            agent_name="security",
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

    print(f"  [Security Agent] Found {len([c for c in all_comments if c['comment'] != 'No issues found'])} issues")
    return all_comments