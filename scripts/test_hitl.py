"""
Test HITL gate on existing held_for_human comments.
Usage: python scripts/test_hitl.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_session
from db.models import ReviewComment, ReviewRun
from orchestration.hitl_gate import run_hitl_gate, get_held_comments


def main():
    run_id = int(input("Enter review_run_id: "))

    # Show current state before HITL
    with get_session() as session:
        all_comments = session.query(ReviewComment).filter_by(
            review_run_id=run_id
        ).all()

        print(f"\nCurrent state of all comments for run_id={run_id}:")
        print("="*55)
        for c in all_comments:
            print(f"  [{c.agent_name}] {c.file_path}")
            print(f"  Status: {c.status} | Confidence: {c.confidence_score}")
            print()

    # Show held comments
    held = get_held_comments(run_id)
    print(f"Comments held for human review: {len(held)}")

    if not held:
        print("No held comments found!")
        print("Either scorer hasn't run yet, or all comments were auto_posted/rejected.")
        return

    # Ask user — interactive or auto mode
    mode = input("\nRun in [i=interactive / a=auto approve all]: ").strip().lower()
    auto = mode in ["a", "auto"]

    # Run HITL gate
    result = run_hitl_gate(run_id, auto_approve_all=auto)

    # Show final state after HITL
    print("\nFINAL STATE after HITL:")
    print("="*55)
    with get_session() as session:
        all_comments = session.query(ReviewComment).filter_by(
            review_run_id=run_id
        ).all()
        for c in all_comments:
            status_icon = {
                "auto_posted": "✅",
                "approved": "✅",
                "rejected": "❌",
                "held_for_human": "⏳",
                "pending": "🔄"
            }.get(c.status, "?")
            print(f"  {status_icon} [{c.agent_name}] {c.file_path}")
            print(f"     Status: {c.status} | Confidence: {c.confidence_score}")

        # Run status
        run = session.query(ReviewRun).filter_by(id=run_id).first()
        print(f"\nReview Run status: {run.status}")

    print("\n✅ auto_posted + approved → will be posted to GitHub (Step 8)")
    print("❌ rejected → discarded")

if __name__ == "__main__":
    main()