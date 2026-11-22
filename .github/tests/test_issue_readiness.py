import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from issue_readiness import (
    CROC_VERSION, ROOT, WINDOWS_X64_SHA256, GitHub,
    croc_smoke_passed, reconcile, transport_preflight_blocker,
)


OWNER = "Hkoado"
HEAD = "a" * 40
MERGED_AT = "2026-01-01T11:00:00Z"
CHECKED_AT = "2026-01-01T10:00:00Z"
REPORT = "bench/preflight/readiness.json"


class GitHubFixture(GitHub):
    def __init__(self, squash_commit):
        super().__init__("https://api.example.invalid", f"{OWNER}/Ratatoss", "fake-token")
        self.target = {"number": 6, "state": "open", "labels": [{"name": "blocked"}, {"name": "transport"}],
                       "assignees": [{"login": "worker"}]}
        self.dependency = {"number": 5, "repository_url": self.repo_url,
                           "state": "closed", "state_reason": "completed"}
        self.dependencies = [self.dependency]
        self.merge = {"number": 42, "title": "[#5] Deliver adapter", "body": "Closes #5", "state": "closed",
                      "merged": True, "merged_at": MERGED_AT, "base": {"ref": "main"}, "head": {"sha": HEAD},
                      "user": {"login": OWNER}, "merged_by": {"login": OWNER}, "merge_commit_sha": squash_commit}
        self.prs = {42: self.merge}
        self.rules = [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "CI", "integration_id": 15368}],
        }}, {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"]}}]
        self.reviews = [{"id": 1, "user": {"login": "reviewer"}, "author_association": "COLLABORATOR",
                         "state": "APPROVED", "commit_id": HEAD, "submitted_at": CHECKED_AT}]
        self.checks = [{"id": 1, "name": "CI", "app": {"id": 15368}, "conclusion": "success",
                        "started_at": CHECKED_AT, "completed_at": CHECKED_AT}]
        self.writes = []
        self.fail_removal = False
        self.graphql_merge_sha = squash_commit

    def request(self, url, *, method="GET", payload=None):
        if url == self.graphql_url and method == "POST":
            assert payload["variables"] == {"owner": OWNER, "repo": "Ratatoss", "number": 42}
            assert "mergeCommit { oid }" in payload["query"]
            commit = {"oid": self.graphql_merge_sha} if self.graphql_merge_sha else None
            return {"data": {"repository": {"pullRequest": {"mergeCommit": commit}}}}
        parsed = urlsplit(url.removeprefix(self.repo_url))
        path = parsed.path
        match path, method:
            case "/issues", "GET":
                query = parse_qs(parsed.query)
                assert query["state"] == ["open"] and query["labels"] == ["blocked"]
                return [self.target] if {"name": "blocked"} in self.target["labels"] else []
            case "/issues/6", "GET":
                return self.target
            case "/rules/branches/main", "GET":
                return self.rules
            case "/issues/6/dependencies/blocked_by", "GET":
                return self.dependencies
            case "/issues/5/timeline", "GET":
                return [{"event": "cross-referenced", "source": {"issue": {
                    "number": number, "repository_url": self.repo_url, "pull_request": {},
                }}} for number in self.prs]
            case "/pulls/42/reviews", "GET":
                return self.reviews
            case "/issues/6/labels", "POST":
                self.writes.append((method, payload))
                self.target["labels"].append({"name": payload["labels"][0]})
                return self.target["labels"]
            case "/issues/6/labels/blocked", "DELETE":
                self.writes.append((method, "blocked"))
                if self.fail_removal:
                    raise HTTPError(url, 503, "Fixture error", None, None)
                self.target["labels"].remove({"name": "blocked"})
                return None
        if path == f"/commits/{HEAD}/check-runs":
            return {"check_runs": self.checks}
        if path.startswith("/pulls/"):
            return self.prs[int(path.rsplit("/", 1)[-1])]
        raise AssertionError(f"Unexpected API call: {method} {url}")


class IssueReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = Path(directory.name).resolve()
        cls.git("init", "--quiet")
        cls.git("commit", "--allow-empty", "--quiet", "-m", "Initial commit")
        cls.git("commit", "--allow-empty", "--quiet", "-m", "Squash delivery")
        cls.sha = cls.git("rev-parse", "HEAD").strip()

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                        "-c", "commit.gpgsign=false", *args], cwd=cls.root, text=True)

    def setUp(self):
        self.github = GitHubFixture(self.sha)
        self.policy = {"inputs": {"6": {"blocked_by": [5], "reports": {REPORT: ["lab"]}}}, "outputs": {}}
        self.report = self.root / REPORT
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.evidence = self.report.with_name("observations.json")
        self.evidence.write_bytes(b"fixture observation")
        self.result = {"status": "pass", "evidence": {self.evidence.name: hashlib.sha256(
            self.evidence.read_bytes()).hexdigest()}}
        self.write_report()

    def write_report(self):
        self.report.write_text(json.dumps({"checks": {"lab": self.result}}), encoding="utf-8")

    def reconcile(self, *, dry_run=False):
        return list(reconcile(self.github, self.root, self.policy, dry_run=dry_run))

    def assert_blocked(self, reason):
        self.assertIn(reason, self.reconcile()[0])
        self.assertEqual(self.github.writes, [])

    def test_dry_run_then_automatically_promotes_without_input_comments(self):
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])
        self.assertEqual(self.github.writes, [])
        self.assertEqual(self.reconcile(), ["#6 moved from blocked to ready"])
        self.assertEqual(self.github.target["labels"], [{"name": "transport"}, {"name": "ready"}])
        self.assertEqual(self.reconcile(), [])

    def test_open_or_not_planned_dependency_blocks(self):
        self.github.dependency["state"] = "open"
        self.assert_blocked("#5 needs to be closed as completed")
        self.github.dependency.update(state="closed", state_reason="not_planned")
        self.assert_blocked("#5 needs to be closed as completed")

    def test_closure_or_unrelated_pr_does_not_prove_delivery(self):
        self.github.merge.update(title="[#25] Another delivery", body="Refs #5")
        self.assert_blocked("#5 needs a linked delivery PR")
        self.github.merge["body"] = "Closes https://github.com/Hkoado/Ratatoss/issues/5"
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])

    def test_unmerged_output_pr_blocks_even_with_another_merged_output(self):
        self.github.prs[43] = dict(self.github.merge, number=43, state="open", merged=False)
        self.assert_blocked("PR #43 needs a merge by an authorized account into main")

    def test_delegate_merge_is_eligible_with_approval_and_ci(self):
        self.github.merge.update(user={"login": "worker"}, merged_by={"login": "NguyenHuy1804"})
        self.github.reviews[0]["user"] = {"login": OWNER}
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])
        self.github.reviews[0]["user"] = {"login": "NguyenHuy1804"}
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])

    def test_delegate_approval_requires_a_different_author_and_a_current_review(self):
        delegate = "NguyenHuy1804"
        self.github.merge["user"] = {"login": "worker"}
        review = self.github.reviews[0]
        review["user"] = {"login": delegate}
        for change in ({"commit_id": "b" * 40}, {"state": "DISMISSED"}, {"author_association": "NONE"}):
            with self.subTest(change=change):
                self.github.reviews = [dict(review, **change)]
                self.assert_blocked("lacks approval on the final PR commit before merge")

        self.github.reviews = [review]
        self.github.merge["user"] = {"login": delegate}
        self.assert_blocked("lacks approval on the final PR commit before merge")
        review["user"] = {"login": OWNER}
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])

    def test_merge_requires_authorized_account_main_and_a_commit_reachable_in_main(self):
        for fields, reason in (({"base": {"ref": "other"}}, "merge by an authorized account into main"),
                               ({"merged_by": {"login": "worker"}}, "merge by an authorized account into main"),
                               ({"merge_commit_sha": "b" * 40}, "squash commit in main history")):
            with self.subTest(fields=fields):
                previous = self.github.merge.copy()
                self.github.merge.update(fields)
                self.assert_blocked(reason)
                self.github.merge.update(previous)

    def test_missing_rest_merge_sha_is_checked_through_graphql(self):
        del self.github.merge["merge_commit_sha"]
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])
        self.github.graphql_merge_sha = "b" * 40
        self.assert_blocked("needs a squash commit in main history")
        self.github.graphql_merge_sha = None
        self.assert_blocked("has no merge commit SHA in GitHub")

    def test_stale_dismissed_or_post_merge_review_blocks(self):
        for changes in ({"commit_id": "b" * 40}, {"state": "DISMISSED"},
                        {"submitted_at": "2026-01-01T12:00:00Z"}):
            with self.subTest(changes=changes):
                original = self.github.reviews[0].copy()
                self.github.reviews[0].update(changes)
                self.assert_blocked("lacks approval on the final PR commit before merge")
                self.github.reviews[0] = original

    def test_failed_or_wrong_app_check_blocks(self):
        good = self.github.checks[0]
        self.github.checks.append(dict(good, id=2, conclusion="failure"))
        self.assert_blocked("lacks passing required CI")
        self.github.checks = [dict(good, app={"id": 1})]
        self.assert_blocked("lacks passing required CI")

    def test_report_needs_passing_case_and_matching_raw_evidence(self):
        self.report.unlink()
        self.assert_blocked("missing report")
        self.result["status"] = "blocked"
        self.write_report()
        self.assert_blocked("needs a passing result and evidence for lab")
        self.result["status"] = "pass"
        self.write_report()
        self.evidence.write_bytes(b"changed observation")
        self.assert_blocked("has an evidence hash mismatch for lab")

    def test_unconfigured_issue_or_missing_relationship_stays_blocked(self):
        self.github.dependencies = []
        self.assert_blocked("required relationships are missing")
        self.policy["inputs"].clear()
        self.assert_blocked("has no input checks configured")

    def test_external_dependency_and_missing_assignee_block(self):
        self.github.target["assignees"] = []
        self.assert_blocked("needs exactly one assignee")
        self.github.target["assignees"] = [{"login": "worker"}]
        self.github.dependency["repository_url"] = "https://api.example.invalid/repos/Other/Ratatoss"
        self.assert_blocked("has a dependency in another repository")

    def test_completed_decision_uses_reviewed_adr(self):
        self.policy["outputs"]["5"] = {"decision": "decision.md"}
        self.github.prs.clear()
        self.assert_blocked("needs its adopted decision on main")
        decision = self.root / "decision.md"
        self.addCleanup(decision.unlink)
        decision.write_text("fixture adopted decision", encoding="utf-8")
        self.assertEqual(self.reconcile(dry_run=True), ["#6 is eligible for ready (dry run)"])

    def test_r01_checked_in_smoke_report(self):
        policy = json.loads((ROOT / ".github/issue-readiness.json").read_text(encoding="utf-8"))
        self.assertTrue(croc_smoke_passed(ROOT / policy["outputs"]["5"]["croc_smoke"]))

    def test_transport_can_start_with_locked_inputs_before_measuring_overlap(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            folder = Path(directory)
            name = folder.name
            self.assertIn("missing lab preflight", transport_preflight_blocker(self.root, name))
            inventory = folder / "endpoints.json"
            inventory.write_text(json.dumps({"A": "a" * 64, "B": "b" * 64, "C": "c" * 64}), encoding="utf-8")
            for metadata in ("relay.json", "network.json"):
                (folder / metadata).write_text("fixture metadata", encoding="utf-8")
            profile = {
                "croc_version": CROC_VERSION,
                "croc_sha256": WINDOWS_X64_SHA256, "relay_config": "relay.json",
                "network_profile": "network.json",
            }
            profile_path = folder / "profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            self.assertIsNone(transport_preflight_blocker(self.root, name))
            (folder / "network.json").unlink()
            self.assertIn("needs the locked network_profile file", transport_preflight_blocker(self.root, name))
            profile_path.write_text(json.dumps(dict(profile, croc_sha256="f" * 64)), encoding="utf-8")
            self.assertIn("needs the pinned Croc version and SHA-256", transport_preflight_blocker(self.root, name))
            inventory.write_text(json.dumps({"A": "a" * 64, "B": "a" * 64, "C": "c" * 64}), encoding="utf-8")
            self.assertIn("needs three distinct endpoints", transport_preflight_blocker(self.root, name))

    def test_retry_can_complete_partial_label_update(self):
        self.github.fail_removal = True
        lines = reconcile(self.github, self.root, self.policy, dry_run=False)
        self.assertEqual(next(lines), "#6: GitHub verification or update failed (HTTP 503)")
        with self.assertRaises(RuntimeError):
            next(lines)
        self.assertIn({"name": "blocked"}, self.github.target["labels"])
        self.github.fail_removal = False
        self.assertEqual(self.reconcile(), ["#6 moved from blocked to ready"])
        self.assertEqual(self.github.writes, [("POST", {"labels": ["ready"]}),
                                             ("DELETE", "blocked"), ("DELETE", "blocked")])
