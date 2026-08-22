"""
Updated gh_integration/webhook.py
Serves React frontend + API + GitHub webhook — all in one FastAPI app.
"""
import os, sys, hmac, hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AURA Platform")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# ── CORS ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security ────────────────────────────────────────────────
def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Pipeline ────────────────────────────────────────────────
async def run_review_pipeline(repo_name: str, pr_number: int, commit_sha: str):
    print(f"\n[Pipeline] Starting — {repo_name} PR #{pr_number}")
    try:
        from db.connection import get_session
        from db.models import PullRequest, ReviewRun, ReviewComment
        from gh_integration.github_client import (
            get_pr_diff, post_all_approved_comments, post_review_summary
        )
        from agents.retrieval_agent import run_retrieval_agent
        from agents.logic_agent import run_logic_agent
        from agents.security_agent import run_security_agent
        from agents.style_agent import run_style_agent
        from agents.test_agent import run_test_agent
        from agents.confidence_scorer import run_confidence_scorer
        from orchestration.hitl_gate import run_hitl_gate

        with get_session() as session:
            pr = session.query(PullRequest).filter_by(repo=repo_name, pr_number=pr_number).first()
            if not pr:
                pr = PullRequest(repo=repo_name, pr_number=pr_number, author="unknown")
                session.add(pr)
                session.flush()
            pr_id = pr.id
            run = ReviewRun(pr_id=pr_id, commit_sha=commit_sha)
            session.add(run)
            session.flush()
            run_id = run.id

        diff_text = get_pr_diff(repo_name, pr_number)
        result = run_retrieval_agent(pr_id=pr_id, diff_text=diff_text)
        chunks = result["chunks"]

        all_comments = []
        all_comments += run_logic_agent(chunks, run_id)
        all_comments += run_security_agent(chunks, run_id)
        all_comments += run_style_agent(chunks, run_id)
        all_comments += run_test_agent(chunks, run_id)

        scoring_results = run_confidence_scorer(run_id, all_comments)
        hitl_results = run_hitl_gate(run_id, auto_approve_all=True)

        with get_session() as session:
            postable = session.query(ReviewComment).filter(
                ReviewComment.review_run_id == run_id,
                ReviewComment.status.in_(["auto_posted", "approved"])
            ).all()
            comments_to_post = [
                {"agent_name": c.agent_name, "file_path": c.file_path,
                 "comment": c.comment, "confidence_score": c.confidence_score,
                 "status": c.status}
                for c in postable
            ]

        post_all_approved_comments(repo_name, pr_number, commit_sha, comments_to_post)
        post_review_summary(
            repo_name, pr_number,
            total_issues=len([c for c in all_comments if c["comment"] != "No issues found"]),
            auto_posted=len(scoring_results["auto_posted"]),
            held_approved=len(hitl_results["approved"]),
            rejected=len(scoring_results["rejected"])
        )
        print(f"[Pipeline] Complete for PR #{pr_number}")

    except Exception as e:
        import traceback
        print(f"[Pipeline] Error: {e}")
        traceback.print_exc()


# ── GitHub Webhook ──────────────────────────────────────────
@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(payload_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    if event_type != "pull_request":
        return {"status": "ignored"}

    action = payload.get("action", "")
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored"}

    repo_name = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    commit_sha = payload["pull_request"]["head"]["sha"]

    background_tasks.add_task(run_review_pipeline, repo_name, pr_number, commit_sha)
    return {"status": "accepted", "pr": pr_number}


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "AURA Platform"}


# ── UI API Routes ───────────────────────────────────────────
@app.get("/api/pr-metadata")
async def get_pr_metadata_route(repo: str, pr_number: int):
    from gh_integration.github_client import get_pr_metadata
    try:
        return get_pr_metadata(repo, pr_number)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/review")
async def trigger_review(payload: dict):
    from db.connection import get_session
    from db.models import PullRequest, ReviewRun, ReviewComment
    from gh_integration.github_client import get_pr_diff
    from agents.retrieval_agent import run_retrieval_agent
    from agents.logic_agent import run_logic_agent
    from agents.security_agent import run_security_agent
    from agents.style_agent import run_style_agent
    from agents.test_agent import run_test_agent
    from agents.confidence_scorer import run_confidence_scorer
    from orchestration.hitl_gate import run_hitl_gate

    repo = payload["repo"]
    pr_number = payload["pr_number"]

    with get_session() as session:
        pr = session.query(PullRequest).filter_by(repo=repo, pr_number=pr_number).first()
        if not pr:
            pr = PullRequest(repo=repo, pr_number=pr_number, author="unknown")
            session.add(pr)
            session.flush()
        pr_id = pr.id
        run = ReviewRun(pr_id=pr_id, commit_sha="ui-triggered")
        session.add(run)
        session.flush()
        run_id = run.id

    diff_text = get_pr_diff(repo, pr_number)
    result = run_retrieval_agent(pr_id=pr_id, diff_text=diff_text)
    chunks = result["chunks"]

    all_comments = []
    all_comments += run_logic_agent(chunks, run_id)
    all_comments += run_security_agent(chunks, run_id)
    all_comments += run_style_agent(chunks, run_id)
    all_comments += run_test_agent(chunks, run_id)

    scoring = run_confidence_scorer(run_id, all_comments)
    run_hitl_gate(run_id, auto_approve_all=True)

    with get_session() as session:
        db_comments = session.query(ReviewComment).filter_by(review_run_id=run_id).all()
        comments_out = [
            {
                "id": c.id,
                "agent_name": c.agent_name,
                "file_path": c.file_path,
                "comment": c.comment,
                "confidence_score": round(c.confidence_score, 3),
                "failure_type": c.failure_type,
                "status": c.status,
            }
            for c in db_comments
            if c.comment != "No issues found"
        ]

    return {
        "comments": comments_out,
        "stats": {
            "total": len(comments_out),
            "auto_posted": len(scoring["auto_posted"]),
            "held": len(scoring["held_for_human"]),
            "rejected": len(scoring["rejected"]),
        }
    }


@app.post("/api/comments/{comment_id}/decide")
async def decide_comment(comment_id: int, payload: dict):
    from db.connection import get_session
    from db.models import ReviewComment, ReviewRun, PullRequest
    from gh_integration.github_client import post_review_comment

    decision = payload.get("decision")
    if decision not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid decision")

    with get_session() as session:
        comment = session.query(ReviewComment).filter_by(id=comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Not found")
        comment.status = decision
        run_id = comment.review_run_id
        c_data = {
            "agent_name": comment.agent_name,
            "file_path": comment.file_path,
            "comment": comment.comment,
            "confidence_score": comment.confidence_score,
        }

    if decision == "approved":
        with get_session() as session:
            run = session.query(ReviewRun).filter_by(id=run_id).first()
            pr = session.query(PullRequest).filter_by(id=run.pr_id).first()
            post_review_comment(
                repo_name=pr.repo, pr_number=pr.pr_number,
                commit_sha=run.commit_sha, file_path=c_data["file_path"],
                comment_body=c_data["comment"], agent_name=c_data["agent_name"],
                confidence_score=c_data["confidence_score"],
            )

    return {"status": "ok", "decision": decision}


@app.get("/api/history")
async def get_history():
    from db.connection import get_session
    from db.models import ReviewComment
    with get_session() as session:
        comments = session.query(ReviewComment).filter(
            ReviewComment.status.in_(["auto_posted", "approved", "rejected"])
        ).order_by(ReviewComment.id.desc()).limit(50).all()
        return [
            {
                "id": c.id,
                "agent_name": c.agent_name,
                "file_path": c.file_path,
                "comment": c.comment[:120],
                "confidence_score": c.confidence_score,
                "status": c.status,
            }
            for c in comments
        ]


@app.get("/api/hitl-queue")
async def get_hitl_queue():
    from db.connection import get_session
    from db.models import ReviewComment
    with get_session() as session:
        comments = session.query(ReviewComment).filter_by(
            status="held_for_human"
        ).order_by(ReviewComment.id.desc()).all()
        return [
            {
                "id": c.id,
                "agent_name": c.agent_name,
                "file_path": c.file_path,
                "comment": c.comment,
                "confidence_score": c.confidence_score,
                "failure_type": c.failure_type,
                "status": c.status,
                "review_run_id": c.review_run_id,
            }
            for c in comments
        ]


# ── Serve React Static Files ────────────────────────────────
# This MUST be after all API routes
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(STATIC_DIR, "static")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Serve React app for all non-API routes."""
        index = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(index)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)