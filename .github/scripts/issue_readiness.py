"""Promote Ratatoss issues after the repository owner's confirmations."""

import json
import os
import re
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ISSUE_COMMENTS = """
query($owner: String!, $repo: String!, $number: Int!, $before: String) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      lastEditedAt
      comments(last: 100, before: $before) {
        pageInfo { hasPreviousPage startCursor }
        nodes { body createdAt isMinimized author { login } editor { login } }
      }
    }
  }
}
"""


class GitHub:
    def __init__(self, api_url, graphql_url, repository, token):
        self.repo_url = f"{api_url}/repos/{repository}"
        self.graphql_url = graphql_url
        self.owner, self.repo = repository.split("/")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Ratatoss-issue-readiness",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def request(self, url, *, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, headers=self.headers, method=method, data=data)
        with urlopen(request, timeout=15) as response:
            return None if response.status == 204 else json.load(response)

    def get(self, path):
        return self.request(self.repo_url + path)

    def items(self, path, **filters):
        page = 1
        while True:
            query = urlencode({**filters, "per_page": 100, "page": page})
            items = self.get(f"{path}?{query}")
            if not isinstance(items, list):
                raise ValueError("GitHub API did not return a list")
            yield from items
            if len(items) < 100:
                return
            page += 1

    def owner_command(self, number, commands):
        before = None
        while True:
            result = self.request(self.graphql_url, method="POST", payload={
                "query": ISSUE_COMMENTS,
                "variables": {"owner": self.owner, "repo": self.repo, "number": number, "before": before},
            })
            if result.get("errors"):
                raise ValueError("GitHub could not resolve issue comments")
            issue = result["data"]["repository"]["issue"]
            comments = issue["comments"]
            for comment in reversed(comments["nodes"]):
                if not from_owner(comment["author"], self.owner):
                    continue
                lines = comment["body"].strip().splitlines()
                words = lines[0].split() if lines else []
                if not words or words[0] not in commands:
                    continue
                created = datetime.fromisoformat(comment["createdAt"])
                edited_by_other = comment["editor"] and not from_owner(comment["editor"], self.owner)
                issue_edited = issue["lastEditedAt"] and created <= datetime.fromisoformat(issue["lastEditedAt"])
                if comment["isMinimized"] or edited_by_other or issue_edited:
                    return (), None
                return words, created
            if not comments["pageInfo"]["hasPreviousPage"]:
                return (), None
            before = comments["pageInfo"]["startCursor"]

    def promote(self, number, labels):
        path = f"{self.repo_url}/issues/{number}/labels"
        if "ready" not in labels:
            result = self.request(path, method="POST", payload={"labels": ["ready"]})
            if not any(label["name"] == "ready" for label in result):
                raise ValueError("GitHub did not confirm the ready label")
        self.request(f"{path}/blocked", method="DELETE")


def from_owner(account, owner):
    return bool(account and account["login"].casefold() == owner.casefold())


def issue_numbers(words):
    if words == ["none"]:
        return set()
    if words and all(re.fullmatch(r"#[1-9][0-9]*", word) for word in words):
        return {int(word[1:]) for word in words}
    return None


def has_evidence_link(word):
    try:
        link = urlsplit(word)
    except ValueError:
        return False
    return link.scheme == "https" and bool(link.hostname) and link.username is None


def dependency_blocker(github, dependency):
    number = dependency["number"]
    if dependency["state"] != "closed" or dependency["state_reason"] != "completed":
        return f"dependency #{number} needs to be closed as completed"

    words, accepted_at = github.owner_command(number, {"/accepted", "/acceptance-revoked"})
    if (len(words) < 3 or words[0] != "/accepted"
            or not has_evidence_link(words[-1])
            or accepted_at < datetime.fromisoformat(dependency["closed_at"])):
        return f"dependency #{number} needs owner acceptance with evidence"
    prs = issue_numbers(words[1:-1])
    if prs is None:
        return f"dependency #{number} needs valid PR numbers or an explicit no-PR acceptance"

    for pr_number in sorted(prs):
        pr = github.get(f"/pulls/{pr_number}")
        if (not pr["merged"] or pr["base"]["ref"] != "main"
                or not from_owner(pr["merged_by"], github.owner)
                or datetime.fromisoformat(pr["merged_at"]) > accepted_at):
            return f"dependency #{number} needs PR #{pr_number} merged by the owner into main before acceptance"
    return None


def readiness_blocker(github, issue):
    number = issue["number"]
    if len(issue["assignees"]) != 1:
        return "needs exactly one assignee"
    words, _ = github.owner_command(number, {"/inputs-ready", "/inputs-pending"})
    if not words or words[0] != "/inputs-ready":
        return "needs current owner confirmation of inputs"

    dependencies = list(github.items(f"/issues/{number}/dependencies/blocked_by"))
    for dependency in dependencies:
        if dependency["repository_url"].casefold() != github.repo_url.casefold():
            return "has a dependency in another repository"
    if issue_numbers(words[1:]) != {dependency["number"] for dependency in dependencies}:
        return "owner confirmation must match the current GitHub dependencies"

    for dependency in dependencies:
        if dependency["number"] == number:
            return "has a self-dependency"
        if blocker := dependency_blocker(github, dependency):
            return blocker
    return None


def reconcile(github, *, dry_run):
    # Finish pagination before removing labels from the result set.
    candidates = list(github.items("/issues", state="open", labels="blocked"))
    failed = False
    for candidate in candidates:
        if "pull_request" in candidate:
            continue
        number = candidate["number"]
        try:
            issue = github.get(f"/issues/{number}")
            labels = {label["name"] for label in issue["labels"]}
            if issue["state"] != "open" or "blocked" not in labels:
                continue
            if blocker := readiness_blocker(github, issue):
                yield f"#{number} remains blocked: {blocker}"
            elif dry_run:
                yield f"#{number} is eligible for ready (dry run)"
            else:
                github.promote(number, labels)
                yield f"#{number} moved from blocked to ready"
        except (HTTPError, URLError, OSError, KeyError, TypeError, ValueError) as error:
            yield f"#{number}: {api_failure(error)}"
            failed = True
    if failed:
        raise RuntimeError("Some issues could not be verified or updated")


def api_failure(error):
    if isinstance(error, HTTPError):
        error.close()
        return f"GitHub verification or update failed (HTTP {error.code})"
    return f"GitHub verification or update failed ({type(error).__name__})"


def main():
    lines = []
    status = 0
    try:
        github = GitHub(os.environ["GITHUB_API_URL"], os.environ["GITHUB_GRAPHQL_URL"],
                        os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
        lines.extend(reconcile(github, dry_run=os.environ.get("DRY_RUN") == "true"))
    except RuntimeError as error:
        lines.append(str(error))
        status = 1
    except (HTTPError, URLError, OSError, KeyError, TypeError, ValueError) as error:
        lines.append(api_failure(error))
        status = 1

    print("\n".join(lines or ["No open issues labeled blocked"]))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write("## Issue readiness\n\n")
            output.writelines(f"- {line}\n" for line in lines or ["No open issues labeled blocked"])
    return status


if __name__ == "__main__":
    sys.exit(main())
