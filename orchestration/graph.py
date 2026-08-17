"""
LangGraph Orchestration — Step 9.
Connects all agents into one graph:
retrieval → [logic, security, style, test] → confidence_scorer → hitl_gate → github_poster
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import TypedDict, List, Dict, Annotated
import operator
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from agents.retrieval_agent import run_retrieval_agent
from agents.logic_agent import run_logic_agent
from agents.security_agent import run_security_agent
from agents.style_agent import run_style_agent
from agents.test_agent import run_test_agent
from agents.confidence_scorer import run_confidence_scorer, print_scoring_summary
from orchestration.hitl_gate import run_hitl_gate
from gh_integration.github_client import post_all_approved_comments, post_review_summary
from db.connection import get_session
from db.models import PullRequest, ReviewRun, ReviewComment

load_dotenv()


# -------------------------------------------------------------------
# 1. STATE — shared dict that flows through every node
# -------------------------------------------------------------------

class AgentState(TypedDict):
    # Input
    repo_name: str
    pr_number: int
    commit_sha: str

    # Set after DB setup
    pr_id: int
    run_id: int

    # Set after retrieval
    diff_text: str
    chunks: List[Dict]

    # Accumulated comments from all agents
    # Annotated[list, operator.add] = auto-merge lists from parallel nodes
    all_comments: Annotated[List[Dict], operator.add]

    # Set after scoring
    scoring_results: Dict

    # Set after HITL
    hitl_results: Dict

    # Final
    post_results: Dict


# -------------------------------------------------------------------
# 2. NODES — one function per step
# -------------------------------------------------------------------

def setup_node(state: AgentState) -> Dict:
    """Store PR + create review run in DB."""
    print(f"\n[Graph] Setting up PR #{state['pr_number']} in DB...")

    with get_session() as session:
        pr = session.query(PullRequest).filter_by(
            repo=state["repo_name"],
            pr_number=state["pr_number"]
        ).first()

        if not pr:
            pr = PullRequest(
                repo=state["repo_name"],
                pr_number=state["pr_number"],
                commit_sha=state["commit_sha"],
                author="unknown"
            )
            session.add(pr)
            session.flush()

        pr_id = pr.id
        run = ReviewRun(pr_id=pr_id, commit_sha=state["commit_sha"])
        session.add(run)
        session.flush()
        run_id = run.id

    print(f"[Graph] PR id={pr_id}, run id={run_id}")
    return {"pr_id": pr_id, "run_id": run_id}


def retrieval_node(state: AgentState) -> Dict:
    """Parse diff, embed chunks, store in DB."""
    print(f"\n[Graph] Running retrieval agent...")
    result = run_retrieval_agent(
        pr_id=state["pr_id"],
        diff_text=state["diff_text"]
    )
    return {"chunks": result["chunks"]}


def logic_node(state: AgentState) -> Dict:
    """Logic agent reviews all chunks."""
    print(f"\n[Graph] Running logic agent...")
    comments = run_logic_agent(state["chunks"], state["run_id"])
    return {"all_comments": comments}


def security_node(state: AgentState) -> Dict:
    """Security agent reviews all chunks."""
    print(f"\n[Graph] Running security agent...")
    comments = run_security_agent(state["chunks"], state["run_id"])
    return {"all_comments": comments}


def style_node(state: AgentState) -> Dict:
    """Style agent reviews all chunks."""
    print(f"\n[Graph] Running style agent...")
    comments = run_style_agent(state["chunks"], state["run_id"])
    return {"all_comments": comments}


def test_node(state: AgentState) -> Dict:
    """Test agent reviews all chunks."""
    print(f"\n[Graph] Running test agent...")
    comments = run_test_agent(state["chunks"], state["run_id"])
    return {"all_comments": comments}


def scorer_node(state: AgentState) -> Dict:
    """Confidence scorer — apply 2x2 framework."""
    print(f"\n[Graph] Running confidence scorer...")
    results = run_confidence_scorer(state["run_id"], state["all_comments"])
    print_scoring_summary(results)
    return {"scoring_results": results}


def hitl_node(state: AgentState) -> Dict:
    """Human-in-the-loop gate."""
    print(f"\n[Graph] Running HITL gate...")
    results = run_hitl_gate(
        review_run_id=state["run_id"],
        auto_approve_all=False  # interactive by default
    )
    return {"hitl_results": results}


def github_post_node(state: AgentState) -> Dict:
    """Post approved comments to GitHub."""
    print(f"\n[Graph] Posting comments to GitHub...")

    # Fetch all auto_posted + approved comments from DB
    with get_session() as session:
        postable = session.query(ReviewComment).filter(
            ReviewComment.review_run_id == state["run_id"],
            ReviewComment.status.in_(["auto_posted", "approved"])
        ).all()

        comments_to_post = [
            {
                "agent_name": c.agent_name,
                "file_path": c.file_path,
                "comment": c.comment,
                "confidence_score": c.confidence_score,
                "status": c.status
            }
            for c in postable
        ]

    post_results = post_all_approved_comments(
        repo_name=state["repo_name"],
        pr_number=state["pr_number"],
        commit_sha=state["commit_sha"],
        comments=comments_to_post
    )

    # Post summary
    scoring = state.get("scoring_results", {})
    hitl = state.get("hitl_results", {})
    post_review_summary(
        repo_name=state["repo_name"],
        pr_number=state["pr_number"],
        total_issues=len(state["all_comments"]),
        auto_posted=len(scoring.get("auto_posted", [])),
        held_approved=len(hitl.get("approved", [])),
        rejected=len(scoring.get("rejected", []))
    )

    return {"post_results": post_results}


# -------------------------------------------------------------------
# 3. GRAPH — wire nodes together
# -------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("setup", setup_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("logic", logic_node)
    graph.add_node("security", security_node)
    graph.add_node("style", style_node)
    graph.add_node("test", test_node)
    graph.add_node("scorer", scorer_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("github_post", github_post_node)

    # Entry point
    graph.set_entry_point("setup")

    # Linear flow: setup → retrieval → agents → scorer → hitl → post
    graph.add_edge("setup", "retrieval")

    # After retrieval — all 4 agents run
    graph.add_edge("retrieval", "logic")
    graph.add_edge("retrieval", "security")
    graph.add_edge("retrieval", "style")
    graph.add_edge("retrieval", "test")

    # After all agents — scorer
    graph.add_edge("logic", "scorer")
    graph.add_edge("security", "scorer")
    graph.add_edge("style", "scorer")
    graph.add_edge("test", "scorer")

    # scorer → hitl → post → end
    graph.add_edge("scorer", "hitl")
    graph.add_edge("hitl", "github_post")
    graph.add_edge("github_post", END)

    return graph.compile()


# -------------------------------------------------------------------
# 4. MAIN ENTRY POINT
# -------------------------------------------------------------------

def run_pr_review(
    repo_name: str,
    pr_number: int,
    diff_text: str,
    commit_sha: str = "manual"
) -> Dict:
    """
    Run the full review pipeline for one PR.
    Called by webhook or manually for testing.
    """
    graph = build_graph()

    initial_state = {
        "repo_name": repo_name,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "diff_text": diff_text,
        "pr_id": 0,
        "run_id": 0,
        "chunks": [],
        "all_comments": [],
        "scoring_results": {},
        "hitl_results": {},
        "post_results": {}
    }

    print(f"\n{'='*55}")
    print(f"PR REVIEW AGENT — {repo_name} PR #{pr_number}")
    print(f"{'='*55}")

    final_state = graph.invoke(initial_state)

    print(f"\n{'='*55}")
    print(f"REVIEW COMPLETE")
    print(f"Posted: {len(final_state['post_results'].get('posted', []))} comments")
    print(f"Failed: {len(final_state['post_results'].get('failed', []))} comments")
    print(f"{'='*55}")

    return final_state