"""
Human-in-the-Loop (HITL) Gate — Step 7 of the review pipeline.

Flow:
1. Fetch all "held_for_human" comments for a review run
2. Show them one by one for human decision
3. Human approves → status = "approved" (will be posted to GitHub)
4. Human rejects → status = "rejected" (discarded)
5. Update review_run status accordingly
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict
from db.connection import get_session
from db.models import ReviewComment, ReviewRun


def get_held_comments(review_run_id: int) -> List[Dict]:
    """
    Fetch all comments that are waiting for human approval.
    These are comments where confidence was low OR failure_type was llm_uncertain.
    """
    with get_session() as session:
        held = session.query(ReviewComment).filter_by(
            review_run_id=review_run_id,
            status="held_for_human"
        ).all()

        return [
            {
                "id": c.id,
                "agent_name": c.agent_name,
                "file_path": c.file_path,
                "line_number": c.line_number,
                "comment": c.comment,
                "confidence_score": c.confidence_score,
                "failure_type": c.failure_type,
                "status": c.status
            }
            for c in held
        ]


def apply_human_decision(comment_id: int, decision: str) -> None:
    """
    Update a single comment's status based on human decision.
    decision = "approved" → will be posted to GitHub
    decision = "rejected" → discarded
    """
    valid_decisions = ["approved", "rejected"]
    if decision not in valid_decisions:
        raise ValueError(f"Invalid decision: {decision}. Must be one of {valid_decisions}")

    with get_session() as session:
        comment = session.query(ReviewComment).filter_by(id=comment_id).first()
        if comment:
            comment.status = decision
            print(f"  Comment id={comment_id} → {decision.upper()}")
        else:
            print(f"  Warning: Comment id={comment_id} not found in DB")


def update_run_status(review_run_id: int) -> None:
    """
    After all human decisions are made, update the review run status.
    If no more held comments → mark run as completed.
    """
    with get_session() as session:
        # Check if any comments still held
        still_held = session.query(ReviewComment).filter_by(
            review_run_id=review_run_id,
            status="held_for_human"
        ).count()

        run = session.query(ReviewRun).filter_by(id=review_run_id).first()
        if run:
            if still_held == 0:
                run.status = "completed"
                print(f"\n  Review run id={review_run_id} → COMPLETED")
            else:
                run.status = "awaiting_human"
                print(f"\n  Review run id={review_run_id} → still AWAITING HUMAN ({still_held} remaining)")


def run_hitl_gate(review_run_id: int, auto_approve_all: bool = False) -> Dict:
    """
    Main HITL entry point.

    Two modes:
    1. auto_approve_all=False (default) → interactive CLI — human reviews each comment
    2. auto_approve_all=True → used in testing to skip manual input

    """
    held_comments = get_held_comments(review_run_id)

    if not held_comments:
        print(f"\n[HITL Gate] No comments held for human review — all automated!")
        update_run_status(review_run_id)
        return {"approved": [], "rejected": []}

    print(f"\n[HITL Gate] {len(held_comments)} comment(s) need your review:")
    print("="*55)

    approved = []
    rejected = []

    for i, comment in enumerate(held_comments, 1):
        print(f"\n--- Comment {i}/{len(held_comments)} ---")
        print(f"Agent:      {comment['agent_name'].upper()}")
        print(f"File:       {comment['file_path']}")
        print(f"Confidence: {comment['confidence_score']}")
        print(f"Type:       {comment['failure_type']}")
        print(f"Issue:\n  {comment['comment']}")
        print("-"*40)

        if auto_approve_all:
            # Test mode — auto approve everything
            decision = "approved"
            print(f"[AUTO MODE] Decision: APPROVED")
        else:
            # Interactive mode — wait for human input
            while True:
                decision = input("Your decision [a=approve / r=reject]: ").strip().lower()
                if decision in ["a", "approve", "approved"]:
                    decision = "approved"
                    break
                elif decision in ["r", "reject", "rejected"]:
                    decision = "rejected"
                    break
                else:
                    print("  Invalid input. Type 'a' to approve or 'r' to reject.")

        apply_human_decision(comment["id"], decision)

        if decision == "approved":
            approved.append(comment)
        else:
            rejected.append(comment)

    update_run_status(review_run_id)

    print(f"\n[HITL Gate] Summary:")
    print(f"  Approved: {len(approved)}")
    print(f"  Rejected: {len(rejected)}")

    return {"approved": approved, "rejected": rejected}