"""
Test all 4 specialist agents with a fake PR diff.
Usage: python scripts/test_agents.py
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
    # 1. Create test PR — get existing one if already there (avoids duplicate error)
    with get_session() as session:
        pr = session.query(PullRequest).filter_by(
            repo="saksham/test-app", pr_number=100
        ).first()

        if not pr:
            pr = PullRequest(
                repo="saksham/test-app",
                pr_number=100,
                title="Add login and password reset",
                author="saksham"
            )
            session.add(pr)
            session.flush()

        pr_id = pr.id

        # Always create a fresh review run
        run = ReviewRun(pr_id=pr_id, commit_sha="def456")
        session.add(run)
        session.flush()
        run_id = run.id

    print(f"Using PR id={pr_id}, new run id={run_id}\n")

    # 2. Retrieval agent
    print("=== RETRIEVAL AGENT ===")
    retrieval_result = run_retrieval_agent(pr_id=pr_id, diff_text=FAKE_DIFF)
    chunks = retrieval_result["chunks"]

    # 3. All 4 specialist agents
    print("\n=== LOGIC AGENT ===")
    logic_comments = run_logic_agent(chunks, run_id)

    print("\n=== SECURITY AGENT ===")
    security_comments = run_security_agent(chunks, run_id)

    print("\n=== STYLE AGENT ===")
    style_comments = run_style_agent(chunks, run_id)

    print("\n=== TEST AGENT ===")
    test_comments = run_test_agent(chunks, run_id)

    # 4. Print all comments
    all_comments = logic_comments + security_comments + style_comments + test_comments
    print("\n" + "="*50)
    print("ALL REVIEW COMMENTS:")
    print("="*50)
    for c in all_comments:
        if c["comment"] != "No issues found":
            print(f"\n[{c['agent_name'].upper()}] {c['file_path']}")
            print(f"  Issue:      {c['comment'][:120]}")
            print(f"  Confidence: {c['confidence_score']}")
            print(f"  Type:       {c['failure_type']}")

    # 5. Show DB count
    with get_session() as session:
        saved = session.query(ReviewComment).filter_by(review_run_id=run_id).all()
        print(f"\nTotal comments saved to DB: {len(saved)}")

    # 6. Cleanup
    with get_session() as session:
        session.query(PullRequest).filter_by(id=pr_id).delete()
    print("Cleaned up test data.")

if __name__ == "__main__":
    main()