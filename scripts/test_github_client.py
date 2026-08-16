"""
Test GitHub client — fetch PR diff and post a test comment.
Usage: python scripts/test_github_client.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gh_integration.github_client import (
    get_pr_metadata,
    get_pr_diff,
    post_review_comment,
    format_comment
)

def main():
    # Apna repo aur PR number daal
    repo_name = input("Repo name (e.g. saksham/my-app): ").strip()
    pr_number = int(input("PR number: ").strip())

    print(f"\n--- Fetching PR metadata ---")
    metadata = get_pr_metadata(repo_name, pr_number)
    print(f"Title:    {metadata['title']}")
    print(f"Author:   {metadata['author']}")
    print(f"Branch:   {metadata['head_branch']} → {metadata['base_branch']}")
    print(f"Files:    {metadata['files_changed']} changed")
    print(f"Changes:  +{metadata['additions']} / -{metadata['deletions']}")

    print(f"\n--- Fetching PR diff ---")
    diff = get_pr_diff(repo_name, pr_number)
    print(f"Diff length: {len(diff)} characters")
    print(f"Preview:\n{diff[:300]}...")

    print(f"\n--- Comment format preview ---")
    sample = format_comment(
        comment_body="MD5 is cryptographically broken — use bcrypt instead",
        agent_name="security",
        confidence_score=0.97
    )
    print(sample)

    # Optional — actually post a test comment
    post = input("\nPost a test comment to this PR? (y/n): ").strip().lower()
    if post == "y":
        success = post_review_comment(
            repo_name=repo_name,
            pr_number=pr_number,
            commit_sha=metadata["commit_sha"],
            file_path="test",
            comment_body="🧪 Test comment from PR Review Agent — ignore this",
            agent_name="logic",
            confidence_score=0.90
        )
        print("Posted!" if success else "Failed to post")

if __name__ == "__main__":
    main()