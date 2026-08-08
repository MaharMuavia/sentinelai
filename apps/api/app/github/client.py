import httpx
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from app.config import settings
import logging

logger = logging.getLogger("sentinel.github")


class GitHubActionResult(BaseModel):
    success: bool
    action_type: str  # COMMENT, ISSUE, PR, DRY_RUN
    url: Optional[str] = None
    message: str


class GitHubClient:
    """
    Official GitHub Actions API Integration Client.
    Posts formatted pre-merge investigation reviews and candidate remediation patches to PRs.
    Strictly reports DRY_RUN when unconfigured without fabricating success claims.
    """

    def __init__(self, token: Optional[str] = None, repository: Optional[str] = None):
        self.token = token or settings.GITHUB_TOKEN
        self.repository = repository or settings.GITHUB_REPOSITORY
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def is_configured(self) -> bool:
        return bool(self.token and self.repository)

    async def post_pr_comment(
        self,
        pr_number: int,
        severity: str,
        recommendation: str,
        evidence_completeness: float,
        proposed_change: str,
        confirmed_consumers_count: int,
        critical_paths: List[str],
        recommended_action: str,
        remediation_diff: Optional[str] = None,
        investigation_id: Optional[str] = None
    ) -> GitHubActionResult:
        """Post a formatted Sentinel AI change impact review comment to a GitHub PR."""

        if pr_number <= 0:
            return GitHubActionResult(
                success=False,
                action_type="COMMENT",
                message=f"Invalid PR number {pr_number} provided."
            )

        comment_body = (
            f"## 🛡️ Sentinel AI Pre-Merge Change Control Analysis\n\n"
            f"**Decision:** `{recommendation}` | **Severity:** `{severity}` | **Evidence Completeness:** `{evidence_completeness}%`\n\n"
            f"### Proposed Schema Change:\n`{proposed_change}`\n\n"
            f"**Confirmed Consumers Affected:** `{confirmed_consumers_count}`\n\n"
            f"### Critical Lineage Paths:\n"
        )
        for path in critical_paths:
            comment_body += f"- `{path}`\n"

        comment_body += f"\n### Recommended Action:\n{recommended_action}\n\n"

        if remediation_diff and remediation_diff.strip():
            comment_body += (
                f"<details><summary><b>View Validated Candidate Patch</b></summary>\n\n"
                f"```diff\n{remediation_diff}\n```\n\n</details>\n\n"
            )

        if investigation_id:
            comment_body += f"*DataHub Audit Record ID: `sentinel-inv-{investigation_id}`*\n"

        if not self.is_configured():
            logger.info("GitHub integration dry-run: GITHUB_TOKEN or GITHUB_REPOSITORY not configured.")
            return GitHubActionResult(
                success=False,
                action_type="DRY_RUN",
                url=None,
                message="GitHub comment prepared (Dry-run mode: GITHUB_TOKEN or GITHUB_REPOSITORY unconfigured)."
            )

        try:
            url = f"https://api.github.com/repos/{self.repository}/issues/{pr_number}/comments"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, headers=self.headers, json={"body": comment_body})
                if res.status_code in (200, 201):
                    data = res.json()
                    return GitHubActionResult(
                        success=True,
                        action_type="COMMENT",
                        url=data.get("html_url"),
                        message=f"Successfully posted Sentinel review comment to PR #{pr_number}."
                    )
                else:
                    return GitHubActionResult(
                        success=False,
                        action_type="COMMENT",
                        message=f"GitHub API error HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as e:
            return GitHubActionResult(
                success=False,
                action_type="COMMENT",
                message=f"Failed to post comment to GitHub API: {str(e)}"
            )
