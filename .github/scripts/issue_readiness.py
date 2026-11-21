"""Promote Ratatoss issues when GitHub records and reviewed inputs pass."""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ratatoss.transport import CROC_VERSION, WINDOWS_X64_SHA256


SHA256 = re.compile(r"[a-f0-9]{64}")
SHA1 = re.compile(r"[a-f0-9]{40}")
MERGE_COMMIT = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) { mergeCommit { oid } }
  }
}
"""


class GitHub:
    def __init__(self, api_url, repository, token, *, graphql_url=None):
        self.repository = repository
        self.repo_url = f"{api_url}/repos/{repository}"
        self.graphql_url = graphql_url or f"{api_url}/graphql"
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

    def items(self, path, *, collection=None, **filters):
        page = 1
        while True:
            query = urlencode({**filters, "per_page": 100, "page": page})
            items = self.get(f"{path}?{query}")
            if collection:
                items = items[collection]
            if not isinstance(items, list):
                raise ValueError("GitHub API did not return a list")
            yield from items
            if len(items) < 100:
                return
            page += 1

    def output_prs(self, number):
        reference = re.compile(
            rf"\b(?:clos(?:e[sd]?)|fix(?:es|ed)?|resolv(?:e[sd]?))\s+"
            rf"(?:#|https://github\.com/{re.escape(self.repository)}/issues/){number}\b",
            re.IGNORECASE,
        )
        seen = set()
        for event in self.items(f"/issues/{number}/timeline"):
            if event["event"] != "cross-referenced":
                continue
            source = (event.get("source") or {}).get("issue") or {}
            if ("pull_request" not in source
                    or source["repository_url"].casefold() != self.repo_url.casefold()):
                continue
            pr_number = source["number"]
            if pr_number in seen:
                continue
            seen.add(pr_number)
            pr = self.get(f"/pulls/{pr_number}")
            # A PR can mention the issue only because it delivers a different ticket.
            if pr["title"].startswith(f"[#{number}]") or reference.search(pr.get("body") or ""):
                if pr["state"] == "open" or pr["merged"]:
                    yield pr

    def merge_commit_sha(self, pr):
        if sha := pr.get("merge_commit_sha"):
            return sha
        # REST can omit the merge SHA even for a merged PR.
        response = self.request(self.graphql_url, method="POST", payload={
            "query": MERGE_COMMIT,
            "variables": {"owner": self.owner, "repo": self.repo, "number": pr["number"]},
        })
        if response.get("errors"):
            raise ValueError("GitHub could not verify the merge commit")
        commit = response["data"]["repository"]["pullRequest"]["mergeCommit"]
        return commit["oid"] if commit else None

    def promote(self, number, labels):
        path = f"{self.repo_url}/issues/{number}/labels"
        if "ready" not in labels:
            result = self.request(path, method="POST", payload={"labels": ["ready"]})
            if not any(label["name"] == "ready" for label in result):
                raise ValueError("GitHub did not confirm the ready label")
        self.request(f"{path}/blocked", method="DELETE")


def from_owner(account, owner):
    return bool(account and account["login"].casefold() == owner.casefold())


def repo_file(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Evidence path leaves the checkout")
    return path if path.is_file() and path.stat().st_size else None


def report_blocker(root, name, required_checks):
    report = repo_file(root, name)
    if report is None:
        return f"missing report {name} ({', '.join(required_checks)})"
    record = json.loads(report.read_text(encoding="utf-8"))
    for check in required_checks:
        result = record.get("checks", {}).get(check, {})
        evidence = result.get("evidence")
        if result.get("status") != "pass" or not isinstance(evidence, dict) or not evidence:
            return f"{name} needs a passing result and evidence for {check}"
        for filename, expected in evidence.items():
            path = repo_file(report.parent, filename)
            if path is None or path == report or not isinstance(expected, str) or not SHA256.fullmatch(expected):
                return f"{name} needs a valid evidence file and SHA-256 for {check}"
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    return f"{name} has an evidence hash mismatch for {check}"
    return None


def croc_smoke_passed(report):
    result = json.loads(report.read_text(encoding="utf-8"))
    cases = {case["name"]: case for case in result["cases"]}
    fixture = result["fixture"]
    required = {"rx-first", "tx-first", "rx-without-tx", "partial-rx-timeout", "retry"}
    if (result["status"] != "pass" or result["tree_clean"] is not True
            or result["expected_croc_sha256"] != WINDOWS_X64_SHA256
            or result["croc"]["version"] != CROC_VERSION
            or result["croc"]["sha256"] != WINDOWS_X64_SHA256
            or not SHA256.fullmatch(fixture["expected_sha256"])
            or not required <= cases.keys()):
        return False
    if any(cases[name]["status"] != "pass" for name in required):
        return False
    if any(cases[name]["received_sha256"] != fixture["expected_sha256"]
           or cases[name]["received_bytes"] != fixture["bytes"] for name in ("rx-first", "tx-first", "retry")):
        return False
    partial = cases["partial-rx-timeout"]
    return (cases["rx-without-tx"]["roles"]["rx"]["status"] == "TRANSPORT_TIMEOUT"
            and partial["roles"]["rx"]["partial_isolated"] is True
            and partial["roles"]["rx"]["process"]["job"]["active_after_stop"] == 0
            and cases["retry"]["retry_of"] == partial["attempt_id"]
            and cases["retry"]["attempt_id"] != partial["attempt_id"])


def transport_preflight_blocker(root, folder):
    expected = (f"{folder}/endpoints.json", f"{folder}/profile.json")
    paths = [repo_file(root, name) for name in expected]
    for name, path in zip(expected, paths):
        if path is None:
            return f"missing lab preflight {name}"
    endpoint_path, profile_path = paths
    endpoints = json.loads(endpoint_path.read_text(encoding="utf-8"))
    if (set(endpoints) != {"A", "B", "C"} or len(set(endpoints.values())) != 3
            or not all(SHA256.fullmatch(value) for value in endpoints.values())):
        return "lab preflight needs three distinct endpoints A/B/C"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("croc_version") != CROC_VERSION or profile.get("croc_sha256") != WINDOWS_X64_SHA256:
        return "lab preflight needs the pinned Croc version and SHA-256"
    for field in ("relay_config", "network_profile"):
        name = profile.get(field)
        if not isinstance(name, str) or not name or repo_file(profile_path.parent, name) is None:
            return f"lab preflight needs the locked {field} file"
    return None


def input_blocker(root, rule):
    for path in rule.get("files", []):
        if repo_file(root, path) is None:
            return f"missing required file {path} on main"
    for path, checks in rule.get("reports", {}).items():
        if blocker := report_blocker(root, path, checks):
            return blocker
    if name := rule.get("croc_smoke"):
        path = repo_file(root, name)
        if path is None or not croc_smoke_passed(path):
            return f"needs passing Croc smoke report {name}"
    if folder := rule.get("transport_preflight"):
        return transport_preflight_blocker(root, folder)
    return None


def main_commit_has_one_parent(root, sha):
    if not isinstance(sha, str) or not SHA1.fullmatch(sha):
        return False
    reachable = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if reachable.returncode:
        return False
    parents = subprocess.check_output(["git", "show", "-s", "--format=%P", sha], cwd=root, text=True)
    return len(parents.split()) == 1


def has_approval(pr, reviews, owner):
    author = pr["user"]["login"].casefold()
    merged_at = datetime.fromisoformat(pr["merged_at"])
    latest = {}
    for review in reviews:
        if (not review.get("user") or not review.get("submitted_at")
                or review["state"] not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}):
            continue
        reviewer = review["user"]["login"].casefold()
        order = (datetime.fromisoformat(review["submitted_at"]), review["id"])
        if order[0] <= merged_at and (reviewer not in latest or order > latest[reviewer][0]):
            latest[reviewer] = (order, review)
    for reviewer, (_, review) in latest.items():
        if review["state"] != "APPROVED" or review["commit_id"] != pr["head"]["sha"]:
            continue
        if author != owner.casefold() and reviewer == owner.casefold():
            return True
        if (author == owner.casefold() and reviewer != author
                and review["author_association"] in {"COLLABORATOR", "MEMBER", "OWNER"}):
            return True
    return False


def has_required_ci(github, pr, required):
    merged_at = datetime.fromisoformat(pr["merged_at"])
    sha = pr["head"]["sha"]
    if not SHA1.fullmatch(sha):
        return False
    latest = {}
    for run in github.items(f"/commits/{sha}/check-runs", collection="check_runs", filter="all"):
        if run["started_at"] and datetime.fromisoformat(run["started_at"]) <= merged_at:
            key = (run["name"], run["app"]["id"])
            if key not in latest or run["id"] > latest[key]["id"]:
                latest[key] = run
    passed = {key for key, run in latest.items()
              if run["conclusion"] == "success" and run["completed_at"]
              and datetime.fromisoformat(run["completed_at"]) <= merged_at}
    return bool(required) and required <= passed


def dependency_blocker(github, root, dependency, output, required):
    number = dependency["number"]
    if decision := output.get("decision"):
        if repo_file(root, decision) is None:
            return f"dependency #{number} needs its adopted decision on main"
        return None

    prs = list(github.output_prs(number))
    if not prs:
        return f"dependency #{number} needs a linked delivery PR"
    for pr in prs:
        label = f"dependency #{number}, PR #{pr['number']}"
        if not pr["merged"] or pr["base"]["ref"] != "main" or not from_owner(pr["merged_by"], github.owner):
            return f"{label} needs a merge by the owner into main"
        merge_sha = github.merge_commit_sha(pr)
        if not merge_sha:
            return f"{label} has no merge commit SHA in GitHub"
        if merge_sha == pr["head"]["sha"] or not main_commit_has_one_parent(root, merge_sha):
            return f"{label} needs a squash commit in main history"
        if not has_approval(pr, github.items(f"/pulls/{pr['number']}/reviews"), github.owner):
            return f"{label} lacks approval on the final PR commit before merge"
        if not has_required_ci(github, pr, required):
            return f"{label} lacks passing required CI on the final PR commit before merge"
    if blocker := input_blocker(root, output):
        return f"dependency #{number}: {blocker}"
    return None


def readiness_blocker(github, root, policy, required, issue):
    number = issue["number"]
    if len(issue["assignees"]) != 1:
        return "needs exactly one assignee"
    rule = policy["inputs"].get(str(number))
    if rule is None:
        return "has no input checks configured on main"

    dependencies = list(github.items(f"/issues/{number}/dependencies/blocked_by"))
    for dependency in dependencies:
        if dependency["repository_url"].casefold() != github.repo_url.casefold():
            return "has a dependency in another repository"
    if not set(rule["blocked_by"]) <= {dependency["number"] for dependency in dependencies}:
        return "required relationships are missing from GitHub Blocked by"

    for dependency in dependencies:
        if dependency["number"] == number:
            return "has a self-dependency"
        if dependency["state"] != "closed" or dependency["state_reason"] != "completed":
            return f"dependency #{dependency['number']} needs to be closed as completed"
    for dependency in dependencies:
        output = policy["outputs"].get(str(dependency["number"]), {})
        if blocker := dependency_blocker(github, root, dependency, output, required):
            return blocker
    return input_blocker(root, rule)


def reconcile(github, root, policy, *, dry_run):
    # Finish pagination before removing labels from the result set.
    candidates = list(github.items("/issues", state="open", labels="blocked"))
    if not candidates:
        return
    rules = github.get("/rules/branches/main")
    required = {(check["context"], check["integration_id"])
                for rule in rules if rule["type"] == "required_status_checks"
                for check in rule["parameters"]["required_status_checks"]}
    squash_only = any(rule["type"] == "pull_request"
                      and rule["parameters"]["allowed_merge_methods"] == ["squash"] for rule in rules)
    if not squash_only:
        raise RuntimeError("Could not verify the squash-only pull request rule on main")
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
            if blocker := readiness_blocker(github, root, policy, required, issue):
                yield f"#{number} remains blocked: {blocker}"
            elif dry_run:
                yield f"#{number} is eligible for ready (dry run)"
            else:
                github.promote(number, labels)
                yield f"#{number} moved from blocked to ready"
        except (HTTPError, URLError, OSError, AttributeError, KeyError, TypeError, ValueError,
                subprocess.SubprocessError) as error:
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
        github = GitHub(os.environ["GITHUB_API_URL"], os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"],
                        graphql_url=os.environ.get("GITHUB_GRAPHQL_URL"))
        policy = json.loads((ROOT / ".github/issue-readiness.json").read_text(encoding="utf-8"))
        lines.extend(reconcile(github, ROOT, policy, dry_run=os.environ.get("DRY_RUN") == "true"))
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
