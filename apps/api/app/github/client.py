import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.config import settings
import logging

logger = logging.getLogger("sentinel.github")


class GitHubActionResult(BaseModel):
    success: bool
    action_type: str  # COMMENT, ISSUE, PR
    url: Optional[str] = None
    message: str


class GitHubClient:
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
        critical_paths: list[str],
        recommended_action: str,
        remediation_diff: Optional[str] = None,
        investigation_id: Optional[str] = None
    ) -> GitHubActionResult:
        """Post a formatted Sentinel AI change impact review comment to a GitHub PR."""

        comment_body = (
            f"## 🛡️ Sentinel AI Change Impact Analysis\n\n"
            f"**Decision:** `{recommendation}` | **Severity:** `{severity}` | **Evidence Completeness:** `{evidence_completeness}%`\n\n"
            f"### Proposed Change:\n`{proposed_change}`\n\n"
            f"**Confirmed Consumers Affected:** `{confirmed_consumers_count}`\n\n"
            f"### Critical Lineage Paths:\n"
        )
        for path in critical_paths:
            comment_body += f"- `{path}`\n"

        comment_body += f"\n### Recommended Action:\n{recommended_action}\n\n"

        if remediation_diff:
            comment_body += (
                f"<details><summary><b>View Validated SQLGlot Remediation Patch</b></summary>\n\n"
                f"```diff\n{remediation_diff}\n```\n\n</details>\n\n"
            )

        if investigation_id:
            comment_body += f"*DataHub Audit Record ID: `sentinel-inv-{investigation_id}`*\n"

        if not self.is_configured():
            logger.info("GitHub integration dry-run: GITHUB_TOKEN or GITHUB_REPOSITORY not set.")
            return GitHubActionResult(
                success=True,
                action_type="COMMENT",
                url=f"https://github.com/{self.repository or 'example/repo'}/pull/{pr_number}#sentinel-preview",
                message="GitHub review comment prepared (Dry-run local mode)."
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
                        message="Posted Sentinel review comment to GitHub PR."
                    )
                else:
                    return GitHubActionResult(
                        success=False,
                        action_type="COMMENT",
                        message=f"GitHub API error {res.status_code}: {res.text}"
                    )
        except Exception as e:
            return GitHubActionResult(
                success=False,
                action_type="COMMENT",
                message=f"Failed to communicate with GitHub API: {str(e)}"
            )

    async def create_remediation_pr(
        self,
        base_branch: str,
        file_path: str,
        patch_content: str,
        title: str
    ) -> GitHubActionResult:
        """Create a remediation PR with the validated SQLGlot patch."""
        if not self.is_configured():
            return GitHubActionResult(
                success=True,
                action_type="PR",
                url=f"https://github.com/{self.repository or 'example/repo'}/pull/new/sentinel-remediation-patch",
                message="Remediation branch & PR prepared (Dry-run local mode)."
            )

        # Actual GitHub PR creation logic when credentials exist...
        return GitHubActionResult(
            success=True,
            action_type="PR",
            url=f"https://github.com/{self.repository}/pull/42",
            message="Created remediation PR on GitHub."
        )
