"""
Confidence Scorer — Step 5 of the review pipeline.

The 2x2 failure framework:
+------------------+------------------+---------------------+
|                  | High Confidence  |  Low Confidence     |
+------------------+------------------+---------------------+
| Engineering Bug  | AUTO POST        | HOLD FOR HUMAN      |
| LLM Uncertain    | HOLD FOR HUMAN   | DISCARD             |
+------------------+------------------+---------------------+

Rules:
- confidence >= 0.85 AND failure_type == engineering → auto_posted
- confidence >= 0.85 AND failure_type == llm_uncertain → held_for_human
- confidence <  0.85 AND failure_type == engineering  → held_for_human
- confidence <  0.85 AND failure_type == llm_uncertain → rejected (discard)
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from db.connection import get_session
from db.models import ReviewComment

# Thresholds — tune these based on how aggressive you want auto-posting
HIGH_CONFIDENCE_THRESHOLD = 0.85
AUTO_POST_REQUIRES = "engineering"


def score_comment(comment: Dict) -> str:
    """
    Apply the 2x2 framework to a single comment.
    Returns the new status string.
    """
    confidence = comment.get("confidence_score", 0.0)
    failure_type = comment.get("failure_type", "llm_uncertain")
    is_no_issue = comment.get("comment", "").strip() == "No issues found"

    # No issue found — no action needed
    if is_no_issue:
        return "rejected"

    high_confidence = confidence >= HIGH_CONFIDENCE_THRESHOLD
    is_engineering = failure_type == AUTO_POST_REQUIRES

    # 2x2 matrix
    if high_confidence and is_engineering:
        return "auto_posted"       # top-left: certain real bug → post it

    elif high_confidence and not is_engineering:
        return "held_for_human"    # top-right: confident but LLM unsure of type

    elif not high_confidence and is_engineering:
        return "held_for_human"    # bottom-left: real bug but LLM not sure enough

    else:
        return "rejected"          # bottom-right: uncertain + LLM unsure → discard


def run_confidence_scorer(review_run_id: int, comments: List[Dict]) -> Dict:
    """
    Score all comments from all agents for one review run.
    Updates status in DB and returns a summary.
    """
    print(f"\n[Confidence Scorer] Scoring {len(comments)} comments...")

    results = {
        "auto_posted": [],
        "held_for_human": [],
        "rejected": []
    }

    with get_session() as session:
        for comment in comments:
            # Skip "No issues found" comments entirely
            if comment.get("comment", "").strip() == "No issues found":
                continue

            new_status = score_comment(comment)

            # Update DB — find the matching row and update its status
            db_comment = session.query(ReviewComment).filter_by(
                review_run_id=review_run_id,
                agent_name=comment["agent_name"],
                file_path=comment["file_path"],
                comment=comment["comment"]
            ).first()

            if db_comment:
                db_comment.status = new_status

            # Bucket the result for summary
            results[new_status].append({
                "agent": comment["agent_name"],
                "file": comment["file_path"],
                "comment": comment["comment"][:80],
                "confidence": comment["confidence_score"],
                "failure_type": comment["failure_type"],
                "status": new_status
            })

    return results


def print_scoring_summary(results: Dict) -> None:
    """Pretty print the scoring results."""
    print("\n" + "="*55)
    print("CONFIDENCE SCORING SUMMARY (2x2 Framework)")
    print("="*55)

    print(f"\n✅ AUTO POST ({len(results['auto_posted'])} comments)")
    print(f"   confidence >= {HIGH_CONFIDENCE_THRESHOLD} + engineering bug")
    for c in results["auto_posted"]:
        print(f"   [{c['agent'].upper()}] {c['file']} (conf: {c['confidence']})")
        print(f"   → {c['comment']}...")

    print(f"\n⏳ HELD FOR HUMAN ({len(results['held_for_human'])} comments)")
    print(f"   low confidence OR llm_uncertain")
    for c in results["held_for_human"]:
        print(f"   [{c['agent'].upper()}] {c['file']} (conf: {c['confidence']}, type: {c['failure_type']})")
        print(f"   → {c['comment']}...")

    print(f"\n❌ REJECTED ({len(results['rejected'])} comments)")
    print(f"   low confidence + llm_uncertain = discarded")
    for c in results["rejected"]:
        print(f"   [{c['agent'].upper()}] {c['file']} (conf: {c['confidence']})")

    print("\n" + "="*55)
    total = len(results['auto_posted']) + len(results['held_for_human']) + len(results['rejected'])
    print(f"Total scored: {total}")
    print(f"Will post automatically: {len(results['auto_posted'])}")
    print(f"Need human review: {len(results['held_for_human'])}")
    print(f"Discarded (noise): {len(results['rejected'])}")