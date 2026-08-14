"""
GitHub Client — Step 8 of the review pipeline.

Two responsibilities:
1. Fetch PR diff and metadata from GitHub
2. Post review comments back to the PR
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Dict, Optional
from github import Github, GithubException
from dotenv import load_dotenv

load_dotenv()

# One GitHub client instance — reused across all calls
github_client = Github(os.getenv("GITHUB_TOKEN"))


# -------------------------------------------------------------------
# 1. FETCH — PR ka diff aur metadata GitHub se laana
# -------------------------------------------------------------------

def get_pr_metadata(repo_name: str, pr_number: int) -> Dict:
    """
    Fetch basic PR info — title, author, base branch, files changed.
    
    repo_name format: "username/repo-name" e.g. "saksham/my-app"
    """
    try:
        repo = github_client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        return {
            "repo": repo_name,
            "pr_number": pr_number,
            "title": pr.title,
            "author": pr.user.login,
            "base_branch": pr.base.ref,       # e.g. "main"
            "head_branch": pr.head.ref,        # e.g. "feature/login"
            "commit_sha": pr.head.sha,         # latest commit
            "files_changed": pr.changed_files,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "state": pr.state,                 # "open", "closed"
            "body": pr.body or ""              # PR description
        }

    except GithubException as e:
        print(f"GitHub API error fetching PR metadata: {e}")
        raise


def get_pr_diff(repo_name: str, pr_number: int) -> str:
    """
    Fetch the raw diff of a PR — exactly what git shows.
    This is what our retrieval agent will parse into chunks.
    """
    try:
        repo = github_client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Get all changed files with their patches (diff content)
        diff_parts = []
        for file in pr.get_files():
            if file.patch:  # some files (binary, too large) have no patch
                diff_parts.append(
                    f"diff --git a/{file.filename} b/{file.filename}\n"
                    f"{file.patch}"
                )
            else:
                diff_parts.append(
                    f"diff --git a/{file.filename} b/{file.filename}\n"
                    f"# Binary file or file too large to display patch"
                )

        full_diff = "\n".join(diff_parts)
        print(f"  Fetched diff: {len(pr.get_files().totalCount)} files changed")
        return full_diff

    except GithubException as e:
        print(f"GitHub API error fetching diff: {e}")
        raise


def get_file_content(repo_name: str, file_path: str, ref: str = "main") -> Optional[str]:
    """
    Fetch full content of a file from GitHub.
    Used by retrieval agent to get more context beyond just the diff.
    
    ref = branch name or commit SHA
    """
    try:
        repo = github_client.get_repo(repo_name)
        file_content = repo.get_contents(file_path, ref=ref)
        return file_content.decoded_content.decode("utf-8")
    except GithubException:
        return None  # file might not exist on that branch


# -------------------------------------------------------------------
# 2. POST — Review comments GitHub PR pe dalna
# -------------------------------------------------------------------

def post_review_comment(
    repo_name: str,
    pr_number: int,
    commit_sha: str,
    file_path: str,
    comment_body: str,
    agent_name: str,
    confidence_score: float
) -> bool:
    """
    Post a single review comment on a specific file in a PR.
    Returns True if successful, False if failed.
    """
    try:
        repo = github_client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Format comment with agent badge + confidence
        formatted_comment = format_comment(comment_body, agent_name, confidence_score)

        # Post as PR review comment on the file
        # Note: posting on file level (not line level) for simplicity
        # Line-level comments need exact diff position — complex to implement
        pr.create_issue_comment(formatted_comment)

        print(f"  Posted comment from {agent_name} agent on {file_path}")
        return True

    except GithubException as e:
        print(f"  Failed to post comment: {e}")
        return False


def post_all_approved_comments(
    repo_name: str,
    pr_number: int,
    commit_sha: str,
    comments: List[Dict]
) -> Dict:
    """
    Post all auto_posted + approved comments to GitHub.
    Called after HITL gate — only approved comments reach here.
    
    Returns summary of what was posted vs failed.
    """
    posted = []
    failed = []

    print(f"\n[GitHub Client] Posting {len(comments)} comments to PR #{pr_number}...")

    for comment in comments:
        # Only post auto_posted and approved — never pending/rejected/held
        if comment.get("status") not in ["auto_posted", "approved"]:
            continue

        success = post_review_comment(
            repo_name=repo_name,
            pr_number=pr_number,
            commit_sha=commit_sha,
            file_path=comment.get("file_path", ""),
            comment_body=comment.get("comment", ""),
            agent_name=comment.get("agent_name", "unknown"),
            confidence_score=comment.get("confidence_score", 0.0)
        )

        if success:
            posted.append(comment)
        else:
            failed.append(comment)

    print(f"\n[GitHub Client] Done — {len(posted)} posted, {len(failed)} failed")
    return {"posted": posted, "failed": failed}


def post_review_summary(
    repo_name: str,
    pr_number: int,
    total_issues: int,
    auto_posted: int,
    held_approved: int,
    rejected: int
) -> None:
    """
    Post a summary comment at the top of the PR — 
    shows overall review stats at a glance.
    """
    try:
        repo = github_client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        summary = f"""## 🤖 AI PR Review Complete

| Metric | Count |
|--------|-------|
| Total issues found | {total_issues} |
| Auto-posted (high confidence) | {auto_posted} |
| Human-approved | {held_approved} |
| Discarded (low confidence) | {rejected} |

> Reviews generated by Multi-Agent PR Review System
> Agents: Logic • Security • Style • Tests
"""
        pr.create_issue_comment(summary)
        print(f"  Posted review summary to PR #{pr_number}")

    except GithubException as e:
        print(f"  Failed to post summary: {e}")


# -------------------------------------------------------------------
# 3. HELPER — Comment formatting
# -------------------------------------------------------------------

def format_comment(
    comment_body: str,
    agent_name: str,
    confidence_score: float
) -> str:
    """
    Add agent badge and confidence indicator to comment.
    Makes it clear which agent flagged what.
    """
    agent_emojis = {
        "logic":    "🧠",
        "security": "🔒",
        "style":    "✨",
        "test":     "🧪"
    }
    emoji = agent_emojis.get(agent_name, "🤖")

    confidence_bar = get_confidence_bar(confidence_score)

    return f"""{emoji} **[{agent_name.upper()} AGENT]**

{comment_body}

---
*Confidence: {confidence_bar} {int(confidence_score * 100)}%*"""


def get_confidence_bar(score: float) -> str:
    """Visual confidence bar — e.g. 0.85 → '████░'"""
    filled = int(score * 5)
    empty = 5 - filled
    return "█" * filled + "░" * empty