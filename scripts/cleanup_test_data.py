
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_session
from db.models import PullRequest

def main():
    with get_session() as session:
        deleted = session.query(PullRequest).filter(
            PullRequest.repo == "saksham/test-app"
        ).delete()
    print(f"Deleted {deleted} test PR(s). Database is clean.")

if __name__ == "__main__":
    main()