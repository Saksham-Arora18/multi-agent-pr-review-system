"""
Test the retrieval agent with a fake PR diff.
Usage: python scripts/test_retrieval.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_session
from db.models import PullRequest, ReviewRun
from agents.retrieval_agent import run_retrieval_agent

# --- Fake PR diff (simulates what GitHub sends) ---
FAKE_DIFF = """
diff --git a/auth/login.py b/auth/login.py
index 83db48f..f735c1a 100644
--- a/auth/login.py
+++ b/auth/login.py
@@ -1,10 +1,20 @@
+import hashlib
+
 def login(username, password):
-    user = db.find(username)
-    if user.password == password:
+    user = db.find(username)
+    hashed = hashlib.md5(password.encode()).hexdigest()
+    if user.password == hashed:
         return generate_token(user)
     return None

+def reset_password(user_id, new_password):
+    # TODO: add auth check
+    db.update(user_id, password=new_password)

diff --git a/utils/helpers.py b/utils/helpers.py
index 1234567..abcdefg 100644
--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -5,3 +5,8 @@
 def format_date(dt):
     return dt.strftime("%Y-%m-%d")
+
+def parse_user_input(raw):
+    # directly used in SQL query — potential injection
+    return f"SELECT * FROM users WHERE name = '{raw}'"
"""

def main():
    # 1. Create a test PR in DB
    with get_session() as session:
        pr = PullRequest(
            repo="saksham/test-app",
            pr_number=99,
            title="Add login and password reset",
            author="saksham"
        )
        session.add(pr)
        session.flush()
        pr_id = pr.id

        run = ReviewRun(pr_id=pr_id, commit_sha="abc123")
        session.add(run)
        session.flush()
        run_id = run.id

    print(f"Created test PR id={pr_id}, run id={run_id}")

    # 2. Run retrieval agent
    result = run_retrieval_agent(pr_id=pr_id, diff_text=FAKE_DIFF)

    # 3. Show results
    print(f"\n--- Retrieval Result ---")
    print(f"Total chunks: {result['total_chunks']}")
    for i, chunk in enumerate(result['chunks']):
        print(f"\nChunk {i+1}: {chunk['file_path']}")
        print(f"  Type: {chunk['chunk_type']}")
        print(f"  Content preview: {chunk['content'][:80]}...")
        print(f"  Similar past chunks found: {len(chunk['similar_past_chunks'])}")

    print("\nRetrieval agent working correctly!")

    # 4. Cleanup
    with get_session() as session:
        session.query(PullRequest).filter_by(id=pr_id).delete()
    print("Cleaned up test data.")

if __name__ == "__main__":
    main()