"""
GitHub Webhook Listener — FastAPI server.

GitHub calls this endpoint when:
- A PR is opened
- A PR gets new commits pushed

This triggers our entire review pipeline.
"""
import os, sys, hmac, hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PR Review Agent Webhook")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


# -------------------------------------------------------------------
# Security — Verify webhook is actually from GitHub
# -------------------------------------------------------------------

def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    GitHub signs every webhook with HMAC-SHA256.
    We verify it to make sure request is from GitHub, not someone random.
    
    If WEBHOOK_SECRET not set, skip verification (dev mode only).
    """
    if not WEBHOOK_SECRET:
        print("Warning: WEBHOOK_SECRET not set — skipping signature verification")
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    # Use compare_digest to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature_header)


# -------------------------------------------------------------------
# Background task — runs pipeline without blocking webhook response
# -------------------------------------------------------------------

async def run_review_pipeline(repo_name: str, pr_number: int, commit_sha: str):
    """
    Full pipeline — called in background after webhook received.
    GitHub expects a response within 10 seconds — 
    we respond immediately and run the heavy work in background.
    """
    print(f"\n[Pipeline] Starting review for {repo_name} PR #{pr_number}")

    try:
        # Import here to avoid circular imports
        from db.connection import get_session
        from db.models import PullRequest, ReviewRun, ReviewComment
        from github.github_client import get_pr_diff, post_all_approved_comments, post_review_summary
        from agents.retrieval_agent import run_retrieval_agent
        from agents.logic_agent import run_logic_agent
        from agents.security_agent import run_security_agent
        from agents.style_agent import run_style_agent
        from agents.test_agent import run_test_agent
        from agents.confidence_scorer import run_confidence_scorer
        from orchestration.hitl_gate import run_hitl_gate

        # 1. Store PR in DB
        with get_session() as session:
            pr = session.query(PullRequest).filter_by(
                repo=repo_name, pr_number=pr_number
            ).first()

            if not pr:
                pr = PullRequest(
                    repo=repo_name,
                    pr_number=pr_number,
                    author="unknown"
                )
                session.add(pr)
                session.flush()

            pr_id = pr.id
            run = ReviewRun(pr_id=pr_id, commit_sha=commit_sha)
            session.add(run)
            session.flush()
            run_id = run.id

        # 2. Fetch diff from GitHub
        diff_text = get_pr_diff(repo_name, pr_number)

        # 3. Retrieval agent
        retrieval_result = run_retrieval_agent(pr_id=pr_id, diff_text=diff_text)
        chunks = retrieval_result["chunks"]

        # 4. All specialist agents
        all_comments = []
        all_comments += run_logic_agent(chunks, run_id)
        all_comments += run_security_agent(chunks, run_id)
        all_comments += run_style_agent(chunks, run_id)
        all_comments += run_test_agent(chunks, run_id)

        # 5. Confidence scorer
        scoring_results = run_confidence_scorer(run_id, all_comments)

        # 6. HITL gate — auto approve for now (webhook mode)
        # In production: send notification to reviewer, wait for API call
        hitl_results = run_hitl_gate(run_id, auto_approve_all=True)

        # 7. Post to GitHub
        postable_comments = [
            c for c in all_comments
            if c.get("status") in ["auto_posted", "approved"]
        ]

        post_result = post_all_approved_comments(
            repo_name=repo_name,
            pr_number=pr_number,
            commit_sha=commit_sha,
            comments=postable_comments
        )

        # 8. Post summary
        post_review_summary(
            repo_name=repo_name,
            pr_number=pr_number,
            total_issues=len([c for c in all_comments if c["comment"] != "No issues found"]),
            auto_posted=len(scoring_results["auto_posted"]),
            held_approved=len(hitl_results["approved"]),
            rejected=len(scoring_results["rejected"])
        )

        print(f"[Pipeline] Complete for PR #{pr_number}")

    except Exception as e:
        print(f"[Pipeline] Error: {e}")
        raise


# -------------------------------------------------------------------
# Webhook endpoint
# -------------------------------------------------------------------

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    GitHub calls this when a PR event happens.
    We verify signature, parse event, trigger pipeline in background.
    """
    # 1. Read raw body for signature verification
    payload_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    # 2. Verify it's really from GitHub
    if not verify_github_signature(payload_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Parse event type
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    # 4. Only handle PR events
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"Event type '{event_type}' not handled"}

    action = payload.get("action", "")

    # Only trigger on new PRs or new commits
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"Action '{action}' not handled"}

    # 5. Extract PR info
    repo_name = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    commit_sha = payload["pull_request"]["head"]["sha"]

    print(f"\nWebhook received: {action} on {repo_name} PR #{pr_number}")

    # 6. Run pipeline in background — respond to GitHub immediately
    background_tasks.add_task(
        run_review_pipeline,
        repo_name=repo_name,
        pr_number=pr_number,
        commit_sha=commit_sha
    )

    # 7. Respond to GitHub within 10 seconds
    return {
        "status": "accepted",
        "message": f"Review pipeline started for PR #{pr_number}"
    }


@app.get("/health")
async def health_check():
    """Simple health check — Render uses this to verify server is up."""
    return {"status": "healthy", "service": "PR Review Agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)