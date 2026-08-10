import re
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel
import httpx
from app.config import settings

logger = logging.getLogger("sentinel.github")


class GitHubActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    DRY_RUN = "DRY_RUN"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    INVALID_PR_URL = "INVALID_PR_URL"


class GitHubActionResult(BaseModel):
    status: GitHubActionStatus
    success: bool
    action_type: str  # COMMENT, ISSUE, PR, DRY_RUN
    url: Optional[str] = None
    message: str
    error_detail: Optional[str] = None


class GitHubClient:
    """
    Official GitHub Actions API Integration Client.
    Parses and validates PR URLs, formats pre-merge investigation reviews, and posts comments to GitHub PRs.
    Strictly enforces repository URL validation and human approval gating.
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

    @staticmethod
    def parse_pr_url(pr_url: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Parse and validate a GitHub PR URL.
        Expected format: https://github.com/<owner>/<repo>/pull/<number>
        Returns (owner_repo, pr_number, error_message).
        """
        if not pr_url:
            return None, None, "PR URL is required."

        pattern = r"^https:\/\/github\.com\/([a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+)\/pull\/(\d+)\/?$"
        match = re.match(pattern, pr_url.strip())
        if not match:
            return None, None, f"Invalid GitHub PR URL format '{pr_url}'. Expected 'https://github.com/<owner>/<repo>/pull/<number>'."

        owner_repo = match.group(1).strip("/")
        try:
            pr_number = int(match.group(2))
            return owner_repo, pr_number, None
        except ValueError:
            return None, None, f"Invalid PR number in URL '{pr_url}'."

    async def post_pr_comment(
        self,
        pr_url: str,
        severity: str,
        recommendation: str,
        evidence_completeness: float,
        evidence_trust: str,
        proposed_change: str,
        confirmed_consumers_count: int,
        critical_paths: List[str],
        recommended_action: str,
        remediation_diff: Optional[str] = None,
        investigation_id: Optional[str] = None,
        approval_granted: bool = False
    ) -> GitHubActionResult:
        """Post a formatted Sentinel AI change impact review comment to a GitHub PR."""

        if not approval_granted:
            return GitHubActionResult(
                status=GitHubActionStatus.AWAITING_APPROVAL,
                success=False,
                action_type="COMMENT",
                message="GitHub comment not executed: persisted approval is required",
            )

        owner_repo, pr_number, parse_err = self.parse_pr_url(pr_url)
        if parse_err or not owner_repo or not pr_number:
            logger.warning(f"GitHub PR URL validation failed: {parse_err}")
            return GitHubActionResult(
                status=GitHubActionStatus.INVALID_PR_URL,
                success=False,
                action_type="COMMENT",
                message=parse_err or "Invalid PR URL"
            )

        # Validate repository match if configured
        if self.repository and owner_repo.lower() != self.repository.lower():
            err_msg = f"Repository mismatch: URL is for '{owner_repo}', but Sentinel is configured for '{self.repository}'."
            logger.warning(err_msg)
            return GitHubActionResult(
                status=GitHubActionStatus.INVALID_PR_URL,
                success=False,
                action_type="COMMENT",
                message=err_msg
            )

        if not self.is_configured():
            logger.info("GitHub integration dry-run: GITHUB_TOKEN unconfigured.")
            return GitHubActionResult(
                status=GitHubActionStatus.DISABLED,
                success=False,
                action_type="DRY_RUN",
                url=None,
                message="GitHub comment prepared (Disabled mode: GITHUB_TOKEN unconfigured)."
            )

        comment_body = (
            f"## 🛡️ Sentinel AI Pre-Merge Change Control Analysis\n\n"
            f"**Decision:** `{recommendation}` | **Severity:** `{severity}` | **Evidence Coverage:** `{evidence_completeness}%` | **Trust:** `{evidence_trust}`\n\n"
            f"### Proposed Schema Change:\n`{proposed_change}`\n\n"
            f"**Confirmed Downstream Consumers Affected:** `{confirmed_consumers_count}`\n\n"
            f"### Critical Lineage Paths:\n"
        )
        for path in critical_paths:
            comment_body += f"- `{path}`\n"

        comment_body += f"\n### Recommended Action:\n{recommended_action}\n\n"

        if remediation_diff and remediation_diff.strip():
            comment_body += (
                f"<details><summary><b>View Candidate Remediation Patch</b></summary>\n\n"
                f"```diff\n{remediation_diff}\n```\n\n</details>\n\n"
            )

        if investigation_id:
            comment_body += f"*Sentinel Audit Record ID: `{investigation_id}`*\n"

        try:
            api_url = f"https://api.github.com/repos/{owner_repo}/issues/{pr_number}/comments"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(api_url, headers=self.headers, json={"body": comment_body})
                if res.status_code in (200, 201):
                    data = res.json()
                    return GitHubActionResult(
                        status=GitHubActionStatus.SUCCESS,
                        success=True,
                        action_type="COMMENT",
                        url=data.get("html_url"),
                        message=f"Successfully posted Sentinel review comment to PR #{pr_number}."
                    )
                else:
                    return GitHubActionResult(
                        status=GitHubActionStatus.FAILED,
                        success=False,
                        action_type="COMMENT",
                        message=f"GitHub API error HTTP {res.status_code}: {res.text[:200]}"
                    )
        except Exception as e:
            return GitHubActionResult(
                status=GitHubActionStatus.FAILED,
                success=False,
                action_type="COMMENT",
                message=f"Failed to post comment to GitHub API: {str(e)}"
            )
