import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_main_merge import Audit, audit_push, main


OWNER = "Hkoado"
REPO = "Hkoado/Ratatoss"
BEFORE = "a" * 40
AFTER = "b" * 40
HEAD = "c" * 40
OLD_HEAD = "d" * 40
PR = 42
EARLY = "2026-11-21T04:00:00Z"
LATER = "2026-11-21T04:01:00Z"
MERGE = "2026-11-21T04:02:00Z"
LATE = "2026-11-21T04:03:00Z"
BASE = {"ref": "main", "repo": {"full_name": REPO}}


def push(actor=OWNER, **overrides):
    return {
        "repository": {"full_name": REPO, "owner": {"login": OWNER}},
        "sender": {"login": actor},
        "ref": "refs/heads/main",
        "before": BEFORE,
        "after": AFTER,
        "commits": [{"id": AFTER}],
        "forced": False,
        "created": False,
        "deleted": False,
        **overrides,
    }


def review(reviewer=OWNER, *, state="APPROVED", sha=HEAD, time=EARLY, id=1, role="COLLABORATOR"):
    return {
        "id": id,
        "user": {"login": reviewer},
        "state": state,
        "commit_id": sha,
        "submitted_at": time,
        "author_association": role,
    }


def dismissal(review_id, *, state="approved", time=LATER):
    return {
        "event": "review_dismissed",
        "created_at": time,
        "dismissed_review": {"review_id": str(review_id), "state": state},
    }


class FakeGitHub:
    def __init__(self, *, author="teammate", merger=OWNER, reviews=(), timeline=(), candidates=None, parents=None):
        self.data = {
            f"/commits/{AFTER}/pulls": candidates if candidates is not None else [
                {"number": PR, "base": BASE, "merge_commit_sha": AFTER}
            ],
            f"/pulls/{PR}": {
                "user": {"login": author},
                "merged": True,
                "merged_at": MERGE,
                "merged_by": {"login": merger},
                "head": {"sha": HEAD},
            },
            f"/pulls/{PR}/reviews": reviews,
            f"/issues/{PR}/timeline": timeline,
            f"/commits/{AFTER}": {"parents": [{"sha": parent} for parent in (parents or [BEFORE])]},
        }

    def get(self, path):
        return self.data[path]

    def items(self, path):
        return iter(self.data[path])


class MergeAuditTests(unittest.TestCase):
    def audit(self, github, event=None):
        return audit_push(event or push(), github, wait=lambda _: None)

    def test_owner_merges_final_head_approved_by_owner(self):
        self.assertEqual(self.audit(FakeGitHub(reviews=[review("hkoado")])), Audit(OWNER, AFTER, PR, OWNER))

    def test_owner_authored_pr_uses_another_collaborator(self):
        self.assertFalse(self.audit(FakeGitHub(author=OWNER, reviews=[review("teammate")])).violations)
        for wrong in (review(), review("outsider", role="NONE")):
            self.assertIn("another repository collaborator",
                          self.audit(FakeGitHub(author=OWNER, reviews=[wrong])).violations[0])

    def test_flags_non_owner_merge_even_if_pr_was_approved(self):
        audit = self.audit(FakeGitHub(merger="teammate", reviews=[review()]), push(actor="teammate"))
        self.assertEqual((audit.actor, audit.pr, audit.merger), ("teammate", PR, "teammate"))
        self.assertIn("other than the repository owner", audit.violations[0])

    def test_flags_wrong_push_actor_and_missing_owner_approval(self):
        audit = self.audit(FakeGitHub(reviews=[review("teammate")]), push(actor="teammate"))
        self.assertEqual(len(audit.violations), 2)
        self.assertIn("No valid approval from the repository owner", audit.violations[1])

    def test_approval_must_match_head_and_predate_merge(self):
        for approval in (review(sha=OLD_HEAD), review(time=LATE), review(time=MERGE)):
            with self.subTest(approval=approval):
                self.assertTrue(self.audit(FakeGitHub(reviews=[approval])).violations)

    def test_latest_decisive_review_counts(self):
        change_request = review(state="CHANGES_REQUESTED", time=LATER, id=2)
        self.assertTrue(self.audit(FakeGitHub(reviews=[change_request, review()])).violations)
        after_merge = review(state="CHANGES_REQUESTED", time=LATE, id=3)
        comment = review(state="COMMENTED", time=LATER, id=2)
        self.assertFalse(self.audit(FakeGitHub(reviews=[comment, after_merge, review()])).violations)

    def test_dismissal_only_withdraws_approval_before_merge(self):
        reviews = [review(state="DISMISSED")]
        self.assertTrue(self.audit(FakeGitHub(reviews=reviews, timeline=[dismissal(1)])).violations)
        self.assertFalse(self.audit(FakeGitHub(reviews=reviews, timeline=[dismissal(1, time=LATE)])).violations)
        with self.assertRaisesRegex(ValueError, "dismissal event"):
            self.audit(FakeGitHub(reviews=reviews))

    def test_dismissed_comment_preserves_previous_approval(self):
        comment = review(state="DISMISSED", time=LATER, id=2)
        timeline = [dismissal(2, state="commented")]
        self.assertFalse(self.audit(FakeGitHub(reviews=[review(), comment], timeline=timeline)).violations)

    def test_flags_direct_push_and_wrong_pr_base(self):
        other_pr = {"number": PR, "merge_commit_sha": AFTER, "base": {**BASE, "ref": "dev"}}
        for candidates in ([], [other_pr]):
            audit = self.audit(FakeGitHub(candidates=candidates), push(actor="teammate"))
            self.assertIsNone(audit.pr)
            self.assertIn("direct push", audit.violations[0])

    def test_flags_multi_commit_non_squash_or_force_push(self):
        github = FakeGitHub(reviews=[review()])
        self.assertTrue(self.audit(github, push(commits=[{"id": OLD_HEAD}, {"id": AFTER}])).violations)
        self.assertTrue(self.audit(github, push(forced=True)).violations)
        self.assertTrue(self.audit(FakeGitHub(reviews=[review()], parents=[BEFORE, OLD_HEAD])).violations)

    def test_main_reports_api_failure_distinctly(self):
        with tempfile.TemporaryDirectory() as temp:
            event = Path(temp, "event.json")
            event.write_text(json.dumps(push()), encoding="utf-8")
            summary = Path(temp, "summary.md")
            env = {"GITHUB_EVENT_PATH": str(event), "GITHUB_STEP_SUMMARY": str(summary),
                   "GITHUB_API_URL": "https://api.github.com", "GH_TOKEN": "synthetic"}
            failure = HTTPError("https://api.github.com", 403, "denied", {}, None)
            with patch.dict(os.environ, env), patch("audit_main_merge.GitHub.get", side_effect=failure):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(), 2)
            self.assertIn("audit unavailable", summary.read_text(encoding="utf-8"))
