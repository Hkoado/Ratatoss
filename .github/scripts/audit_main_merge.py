"""Audit a push to main using GitHub's merge and review records."""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Audit:
    actor: str
    commit: str
    pr: int | None = None
    merger: str | None = None
    violations: tuple[str, ...] = ()


class GitHub:
    def __init__(self, api_url, repo, token):
        self.url = f"{api_url}/repos/{repo}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Ratatoss-main-merge-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get(self, path):
        request = Request(self.url + path, headers=self.headers)
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def items(self, path):
        page = 1
        while True:
            items = self.get(f"{path}?per_page=100&page={page}")
            if not isinstance(items, list):
                raise ValueError("GitHub API did not return a list")
            yield from items
            if len(items) < 100:
                return
            page += 1


def has_approval(pr, reviews, owner):
    author = pr["user"]["login"].casefold()
    merge_time = datetime.fromisoformat(pr["merged_at"])
    decisions = {}

    for review in reviews:
        reviewer = review.get("user")
        submitted_at = review.get("submitted_at")
        if (not reviewer or not submitted_at
                or review["state"] not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}):
            continue
        order = datetime.fromisoformat(submitted_at), review["id"]
        if order[0] >= merge_time:
            continue
        login = reviewer["login"].casefold()
        if login not in decisions or order > decisions[login][0]:
            decisions[login] = order, review

    for login, (_, decision) in decisions.items():
        if decision["state"] != "APPROVED" or decision["commit_id"] != pr["head"]["sha"]:
            continue
        if author != owner and login == owner:
            return True
        if (author == owner and login != owner
                and decision["author_association"] in {"COLLABORATOR", "MEMBER", "OWNER"}):
            return True
    return False


def audit_push(event, github, *, wait=sleep):
    if event["ref"] != "refs/heads/main":
        raise ValueError("Expected a push event for main")

    repo = event["repository"]["full_name"]
    owner = event["repository"]["owner"]["login"].casefold()
    actor = event["sender"]["login"]
    after = event["after"]
    before = event["before"]
    if event["forced"] or event["created"] or event["deleted"]:
        return Audit(actor, after, violations=("Nonstandard update: force push, branch creation or deletion.",))

    commit_ids = [commit["id"] for commit in event["commits"]]
    if commit_ids != [after]:
        return Audit(actor, after, violations=("Expected one new commit from a squash merge.",))

    # GitHub can take a moment to index the association after the push event.
    for attempt in range(5):
        matches = [
            candidate for candidate in github.items(f"/commits/{after}/pulls")
            if candidate["base"]["ref"] == "main"
            and candidate["base"]["repo"]["full_name"].casefold() == repo.casefold()
            and candidate["merge_commit_sha"] == after
        ]
        if matches:
            break
        if attempt < 4:
            wait(3)
    if len(matches) > 1:
        raise ValueError("GitHub returned several PRs for the same merge commit")
    if not matches:
        return Audit(actor, after, violations=("No merged PR matches the main update. Check for a direct push.",))

    number = matches[0]["number"]
    pr = github.get(f"/pulls/{number}")
    if not pr["merged"] or not pr["merged_at"]:
        raise ValueError("GitHub has not confirmed the candidate PR was merged")
    merger = pr["merged_by"]["login"]
    violations = []
    commit = github.get(f"/commits/{after}")
    if [parent["sha"] for parent in commit["parents"]] != [before]:
        violations.append("The commit did not have the previous main tip as its sole parent.")
    if actor.casefold() != owner or merger.casefold() != owner:
        violations.append("The push or PR merge was performed by an account other than the repository owner.")

    if not has_approval(pr, github.items(f"/pulls/{number}/reviews"), owner):
        if pr["user"]["login"].casefold() == owner:
            expected = "another repository collaborator"
        else:
            expected = "the repository owner"
        violations.append(f"No valid approval from {expected} on the final PR commit before merging.")
    return Audit(actor, after, number, merger, tuple(violations))


def report(title, lines):
    print(title)
    for line in lines:
        print(line)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write(f"## {title}\n\n")
            output.writelines(f"- {line}\n" for line in lines)


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        repo = event["repository"]["full_name"]
        github = GitHub(os.environ["GITHUB_API_URL"], repo, os.environ["GH_TOKEN"])
        audit = audit_push(event, github)
    except HTTPError as error:
        report("Main merge audit unavailable", [f"GitHub API returned HTTP {error.code}."])
        return 2
    except (URLError, OSError, ValueError, KeyError, TypeError) as error:
        report("Main merge audit unavailable", [f"Could not verify GitHub records ({type(error).__name__})."])
        return 2

    lines = [f"Push by `{audit.actor}` to `main`, commit `{audit.commit}`."]
    if audit.pr is not None:
        lines.append(f"[PR #{audit.pr}](https://github.com/{repo}/pull/{audit.pr}) merged by `{audit.merger}`.")
    if audit.violations:
        report("Main merge audit flagged this update", lines + list(audit.violations))
        return 1
    report("Main merge audit passed", lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
