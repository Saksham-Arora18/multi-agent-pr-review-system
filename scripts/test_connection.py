import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_session
from db.models import PullRequest



def main():
    with get_session() as session:
        # Insert a dummy PR
        test_pr = PullRequest(
            repo="saksham/test-repo",
            pr_number=1,
            title="Test PR — connection check",
            author="saksham",
        )
        session.add(test_pr)
        session.flush()  # get the auto-generated id without committing yet
        print(f"Inserted test PR with id={test_pr.id}")

        # Read it back
        fetched = session.query(PullRequest).filter_by(repo="saksham/test-repo", pr_number=1).first()
        print(f"Fetched back: {fetched.title} by {fetched.author}")

        # Clean up so we don't leave test data behind
        session.delete(fetched)
        print("Cleaned up test row.")

    print("\nConnection + models working correctly.")

if __name__ == "__main__":
    main()