import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from issue_readiness import GitHub, reconcile


OWNER = "Hkoado"
EVIDENCE = "https://example.invalid/evidence"
CLOSED_AT = "2026-01-01T10:00:00Z"
CONFIRMED_AT = "2026-01-01T11:00:00Z"


def comment(body, *, author=OWNER, editor=None, minimized=False, created=CONFIRMED_AT):
    return {
        "body": body,
        "createdAt": created,
        "isMinimized": minimized,
        "author": {"login": author},
        "editor": {"login": editor} if editor else None,
    }


class GitHubFixture(GitHub):
    def __init__(self):
        super().__init__("https://api.example.invalid", "https://api.example.invalid/graphql",
                         f"{OWNER}/Ratatoss", "fake-token")
        self.target = self.issue(6, state="open", labels=[{"name": "blocked"}, {"name": "transport"}],
                                 assignees=[{"login": "worker"}])
        self.predecessor = self.issue(5, state="closed", state_reason="completed", closed_at=CLOSED_AT)
        self.issues = {5: self.predecessor, 6: self.target}
        self.dependencies = [self.predecessor]
        self.comments = {6: [comment("/inputs-ready #5")], 5: [comment(f"/accepted #42 {EVIDENCE}")]}
        self.edits = {}
        self.pr = {"merged": True, "merged_at": CLOSED_AT, "base": {"ref": "main"},
                   "merged_by": {"login": OWNER}}
        self.writes = []
        self.fail_removal = False

    def issue(self, number, **fields):
        return {"number": number, "repository_url": self.repo_url, "labels": [], **fields}

    def request(self, url, *, method="GET", payload=None):
        if url == self.graphql_url:
            args = payload["variables"]
            number = args["number"]
            comments = self.comments.get(number, [])
            end = int(args["before"]) if args["before"] else len(comments)
            start = max(0, end - 100)
            return {"data": {"repository": {"issue": {
                "lastEditedAt": self.edits.get(number),
                "comments": {"nodes": comments[start:end],
                             "pageInfo": {"hasPreviousPage": start > 0, "startCursor": str(start)}},
            }}}}

        parsed = urlsplit(url.removeprefix(self.repo_url))
        path = parsed.path
        if path == "/issues":
            query = parse_qs(parsed.query)
            assert query["state"] == ["open"] and query["labels"] == ["blocked"]
            candidates = [issue for issue in self.issues.values() if issue["state"] == "open"
                          and any(label["name"] == "blocked" for label in issue["labels"])]
            start = (int(query["page"][0]) - 1) * 100
            return candidates[start:start + 100]
        if path == "/issues/6/dependencies/blocked_by":
            return self.dependencies
        if path == "/pulls/42":
            return self.pr
        if path == "/issues/6/labels" and method == "POST":
            self.writes.append((method, payload))
            self.target["labels"].append({"name": payload["labels"][0]})
            return self.target["labels"]
        if path == "/issues/6/labels/blocked" and method == "DELETE":
            self.writes.append((method, "blocked"))
            if self.fail_removal:
                raise HTTPError(url, 503, "Fixture error", None, None)
            self.target["labels"].remove({"name": "blocked"})
            return None
        if method == "GET" and path.startswith("/issues/"):
            return self.issues[int(path.rsplit("/", 1)[-1])]
        raise AssertionError(f"Unexpected API call: {method} {url}")


class IssueReadinessTests(unittest.TestCase):
    def setUp(self):
        self.github = GitHubFixture()

    def reconcile(self, *, dry_run=False):
        return list(reconcile(self.github, dry_run=dry_run))

    def assert_blocked(self, reason):
        self.assertIn(reason, self.reconcile()[0])
        self.assertEqual(self.github.writes, [])

    def test_dry_run_and_idempotent_promotion_preserve_other_labels(self):
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])
        self.assertEqual(self.github.writes, [])
        self.assertEqual(self.reconcile(), ["#6 moved from blocked to ready"])
        self.assertEqual(self.github.target["labels"], [{"name": "transport"}, {"name": "ready"}])
        self.assertEqual(self.reconcile(), [])

    def test_open_or_not_planned_dependency_blocks(self):
        self.github.predecessor["state"] = "open"
        self.assert_blocked("#5 needs to be closed as completed")
        self.github.predecessor.update(state="closed", state_reason="not_planned")
        self.assert_blocked("#5 needs to be closed as completed")

    def test_closing_dependency_alone_never_unlocks(self):
        self.github.comments[5] = [comment(f"/accepted #42 {EVIDENCE}", author="worker")]
        self.assert_blocked("#5 needs owner acceptance with evidence")
        self.github.comments[5] = [comment("/accepted #42")]
        self.assert_blocked("#5 needs owner acceptance with evidence")
        self.github.comments[5] = [comment(f"/accepted #42 {EVIDENCE}", created="2026-01-01T09:00:00Z")]
        self.assert_blocked("#5 needs owner acceptance with evidence")

    def test_latest_revocation_or_stale_input_blocks(self):
        self.github.comments[6].append(comment("/inputs-pending"))
        self.github.comments[6].append(comment("/inputs-ready #5", author="worker"))
        self.assert_blocked("needs current owner confirmation")
        self.github.comments[6].append(comment("/inputs-ready #5"))
        self.github.edits[6] = CONFIRMED_AT
        self.assert_blocked("needs current owner confirmation")

    def test_edited_or_minimized_comment_cannot_override_previous_confirmation(self):
        for invalid in (comment("/inputs-ready #5", editor="worker"), comment("/inputs-ready #5", minimized=True)):
            with self.subTest(invalid=invalid):
                self.github.comments[6] = [comment("/inputs-ready #5"), invalid]
                self.assert_blocked("needs current owner confirmation")

    def test_new_relationship_requires_updated_confirmation(self):
        self.github.dependencies.append(self.github.issue(23, state="open", state_reason=None))
        self.assert_blocked("must match the current GitHub dependencies")
        self.github.comments[6].append(comment("/inputs-ready #23 #5"))
        self.assert_blocked("#23 needs to be closed as completed")

    def test_external_dependency_and_missing_assignee_block(self):
        self.github.target["assignees"] = []
        self.assert_blocked("needs exactly one assignee")
        self.github.target["assignees"] = [{"login": "worker"}]
        self.github.predecessor["repository_url"] = "https://api.example.invalid/repos/Other/Ratatoss"
        self.assert_blocked("has a dependency in another repository")

    def test_pr_must_be_merged_by_owner_to_main_before_acceptance(self):
        for record in ({"merged": False}, {"base": {"ref": "other"}}, {"merged_by": {"login": "worker"}},
                       {"merged_at": "2026-01-01T12:00:00Z"}):
            with self.subTest(record=record):
                original = self.github.pr.copy()
                self.github.pr.update(record)
                self.assert_blocked("needs PR #42 merged by the owner into main before acceptance")
                self.github.pr = original

    def test_non_code_dependency_and_independent_issue(self):
        self.github.comments[5] = [comment(f"/accepted none {EVIDENCE}")]
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])
        self.github.dependencies = []
        self.assert_blocked("must match the current GitHub dependencies")
        self.github.comments[6].append(comment("/inputs-ready none"))
        self.assertEqual(self.reconcile(), ["#6 moved from blocked to ready"])

    def test_comment_pagination_and_pr_filter(self):
        self.github.comments[6].extend(comment("Unrelated update") for _ in range(100))
        self.github.issues[42] = self.github.issue(42, state="open", pull_request={}, labels=[{"name": "blocked"}])
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])

    def test_retry_can_complete_partial_label_update(self):
        self.github.fail_removal = True
        lines = reconcile(self.github, dry_run=False)
        self.assertEqual(next(lines), "#6: GitHub verification or update failed (HTTP 503)")
        with self.assertRaises(RuntimeError):
            next(lines)
        self.assertIn({"name": "blocked"}, self.github.target["labels"])
        self.github.fail_removal = False
        self.assertEqual(self.reconcile(), ["#6 moved from blocked to ready"])
        self.assertEqual(self.github.writes, [("POST", {"labels": ["ready"]}),
                                             ("DELETE", "blocked"), ("DELETE", "blocked")])
