from app.github.client import GitHubClient


def test_parse_pr_url_rejects_trailing_path_or_fragment():
    assert GitHubClient.parse_pr_url("https://github.com/example/repo/pull/12")[1] == 12
    assert GitHubClient.parse_pr_url("https://github.com/example/repo/pull/12/")[1] == 12
    assert GitHubClient.parse_pr_url("https://github.com/example/repo/pull/12#comment")[1] is None
    assert GitHubClient.parse_pr_url("https://github.com/example/repo/pull/12/extra")[1] is None
