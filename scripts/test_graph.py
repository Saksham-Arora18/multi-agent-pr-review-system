"""
Test full LangGraph pipeline on real GitHub PR.
Usage: python scripts/test_graph.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gh_integration.github_client import get_pr_diff, get_pr_metadata
from orchestration.graph import run_pr_review

def main():
    repo_name = input("Repo name (e.g. Saksham-Arora18/hello): ").strip()
    pr_number = int(input("PR number: ").strip())

    print(f"\nFetching PR from GitHub...")
    metadata = get_pr_metadata(repo_name, pr_number)
    diff_text = get_pr_diff(repo_name, pr_number)

    print(f"PR: {metadata['title']}")
    print(f"Files changed: {metadata['files_changed']}")

    # Run full pipeline
    final_state = run_pr_review(
        repo_name=repo_name,
        pr_number=pr_number,
        diff_text=diff_text,
        commit_sha=metadata["commit_sha"]
    )

if __name__ == "__main__":
    main()