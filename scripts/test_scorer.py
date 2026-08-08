"""
Test confidence scorer end to end.
Usage: python scripts/test_scorer.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_session
from db.models import PullRequest, ReviewRun, ReviewComment
from agents.retrieval_agent import run_retrieval_agent
from agents.logic_agent import run_logic_agent
from agents.security_agent import run_security_agent
from agents.style_agent import run_style_agent
from agents.test_agent import run_test_agent
from agents.confidence_scorer import run_confidence_scorer, print_scoring_summary

FAKE_DIFF = """
diff --git a/auth/login.py b/auth/login.py
--- a/auth/login.py
+++ b/auth/login.py
@@ -1,5 +1,10 @@
+import hashlib
+
 def login(username, password):
     user = db.find(username)
-    if user.password == password:
+    hashed = hashlib.md5(password.encode()).hexdigest()
+    if user.password == hashed:
         return generate_token(user)
     return None

+def reset_password(user_id, new_password):
+    # TODO: add auth check
+    db.update(user_id, password=new_password)

diff --git a/utils/helpers.py b/utils/helpers.py
--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -5,3 +5,8 @@
 def format_date(dt):
     return dt.strftime("%Y-%m-%d")
+
+def parse_user_input(raw):
+    return f"SELECT * FROM users WHERE name = '{raw}'"
"""

def main():
    # 1. Setup PR + run
    with get_session() as session:
        pr = session.query(PullRequest).filter_by(
            repo="saksham/test-app", pr_number=101
        ).first()
        if not pr:
            pr = PullRequest(
                repo="saksham/test-app",
                pr_number=101,
                title="Test scorer PR",
                author="saksham"
            )
            session.add(pr)
            session.flush()
        pr_id = pr.id

        run = ReviewRun(pr_id=pr_id, commit_sha="scorer_test")
        session.add(run)
        session.flush()
        run_id = run.id

    print(f"PR id={pr_id}, run id={run_id}\n")

    # 2. Retrieval
    retrieval_result = run_retrieval_agent(pr_id=pr_id, diff_text=FAKE_DIFF)
    chunks = retrieval_result["chunks"]

    # 3. All agents
    all_comments = []
    all_comments += run_logic_agent(chunks, run_id)
    all_comments += run_security_agent(chunks, run_id)
    all_comments += run_style_agent(chunks, run_id)
    all_comments += run_test_agent(chunks, run_id)

    print(f"\nTotal comments from all agents: {len(all_comments)}")

    # 4. Confidence scorer
    results = run_confidence_scorer(run_id, all_comments)
    print_scoring_summary(results)

    # 5. Show DB final state
    print("\nFINAL DB STATE:")
    with get_session() as session:
        comments = session.query(ReviewComment).filter_by(review_run_id=run_id).all()
        for c in comments:
            print(f"  [{c.agent_name}] {c.file_path} → status: {c.status} (conf: {c.confidence_score})")

    # 6. Cleanup
    with get_session() as session:
        session.query(PullRequest).filter_by(id=pr_id).delete()
    print("\nCleaned up.")

if __name__ == "__main__":
    main()
    