import copy
import json
from pathlib import Path
import unittest

from automation.policy import (active, approved, bundle_id, capacity, check_runs_pass, delivery,
                               human_command, metadata, render_record, reviews, revision)

ROOT = Path(__file__).resolve().parents[1]


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "policy.json").read_text())
        self.policy.update(mode="live")
        self.policy["worker"] = {"login": "worker", "id": 123}
        self.policy["gate"] = {"login": "gate[bot]", "app_id": 456}
        self.issue = {"number": 1, "title": "Improve reading", "body": (ROOT / "templates/proposal.md").read_text(),
                      "state": "open", "labels": [{"name": "proposal"}]}
        self.repo = "ieasybooks/aljam3-web-app"
        self.pull = {"number": 10, "repository": self.repo, "state": "open", "draft": False, "mergeable": True,
                     "base": {"sha": "b" * 40, "ref": "main"}, "current_base": "b" * 40, "base_is_ancestor": True,
                     "head": {"sha": "a" * 40, "repo": {"full_name": self.repo}}, "files": ["app/views/example.rb"],
                     "checks": [{"id": 1, "name": "Aljam3 / CI", "app": {"slug": "github-actions"}, "status": "completed", "conclusion": "success"}],
                     "body": f"Product issue: https://github.com/ieasybooks/aljam3-product/issues/1\nProposal revision: {revision(self.issue)}"}
        self.comments = [self.comment(1, f"/aljam3 approve {revision(self.issue)}")]
        self.add_reviews()

    def comment(self, number, body, worker=False, gate=False):
        actor = self.policy["worker"] if worker else self.policy["owner"]
        if gate:
            actor = {"login": self.policy["gate"]["login"], "id": 4567}
        return {"id": number, "user": actor, "body": body, "created_at": "2026-10-09T10:00:00Z", "updated_at": "2026-10-09T10:00:00Z"}

    def add_reviews(self):
        template = json.loads((ROOT / "templates/review.json").read_text())
        bundle = bundle_id(revision(self.issue), [self.pull])
        for index, role in enumerate(("cto", "qa", "cpo", "ceo"), 2):
            record = {**template, "role": role, "task_id": f"task-{role}", "bundle": bundle}
            self.comments.append(self.comment(index, render_record(record), worker=True))

    def test_valid_delivery_binds_scope_code_and_base(self):
        self.assertEqual(delivery(self.issue, self.comments, [self.pull], self.policy), bundle_id(revision(self.issue), [self.pull]))

    def test_owner_identity_is_numeric_not_display_name(self):
        self.comments[0]["user"] = {"id": 999, "login": "AliOsm"}
        with self.assertRaisesRegex(ValueError, "human approval"):
            approved(self.issue, self.comments, self.policy)

    def test_edited_approval_does_not_authorize(self):
        self.comments[0]["updated_at"] = "later"
        with self.assertRaises(ValueError):
            approved(self.issue, self.comments, self.policy)

    def test_quoted_approval_does_not_authorize(self):
        self.comments[0]["body"] = "> " + self.comments[0]["body"]
        with self.assertRaises(ValueError):
            approved(self.issue, self.comments, self.policy)

    def test_request_for_changes_revokes_approval(self):
        self.comments.append(self.comment(9, f"/aljam3 changes {revision(self.issue)}"))
        with self.assertRaises(ValueError):
            approved(self.issue, self.comments, self.policy)

    def test_new_owner_comment_can_reapprove(self):
        self.comments.extend([self.comment(9, f"/aljam3 changes {revision(self.issue)}"),
                              self.comment(10, f"/aljam3 approve {revision(self.issue)}")])
        approved(self.issue, self.comments, self.policy)

    def test_body_edit_requires_new_approval(self):
        self.issue["body"] += "\nAdditional scope."
        with self.assertRaises(ValueError):
            approved(self.issue, self.comments, self.policy)

    def test_new_head_requires_new_role_evidence(self):
        self.pull["head"]["sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "evidence"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_new_base_requires_new_role_evidence(self):
        self.pull["base"]["sha"] = self.pull["current_base"] = "d" * 40
        with self.assertRaisesRegex(ValueError, "evidence"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_stale_branch_cannot_merge_even_with_reviews(self):
        self.pull["base_is_ancestor"] = False
        with self.assertRaisesRegex(ValueError, "include the current base"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_failed_ci_rerun_overrides_old_success(self):
        self.pull["checks"].append({**self.pull["checks"][0], "id": 2, "conclusion": "failure"})
        with self.assertRaisesRegex(ValueError, "CI has not passed"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_skipped_ci_is_not_success(self):
        self.pull["checks"][0]["conclusion"] = "skipped"
        with self.assertRaises(ValueError):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_lookalike_ci_from_other_app_is_not_accepted(self):
        self.pull["checks"][0]["app"]["slug"] = "fake-actions"
        with self.assertRaises(ValueError):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_malformed_proposal_stops_capacity_count(self):
        self.issue["body"] = "Unstructured proposal"
        with self.assertRaisesRegex(ValueError, "malformed"):
            capacity([self.issue], {}, self.policy)

    def test_kind_cap_applies_even_when_size_has_room(self):
        issues = []
        for n in range(3):
            issue = copy.deepcopy(self.issue)
            issue["number"] = n + 1
            issue["body"] = issue["body"].replace('"kind":"enhancement"', '"kind":"bug"').replace("replace-with-stable-key", f"bug-number-{n}")
            issues.append(issue)
        with self.assertRaisesRegex(ValueError, "kind/bug"):
            capacity(issues, {i["number"]: [] for i in issues}, self.policy)

    def test_approved_closed_work_still_occupies_a_slot(self):
        self.issue["state"] = "closed"
        counts = capacity([self.issue], {1: self.comments}, self.policy)
        self.assertEqual(counts["size"]["small"], 1)

    def test_authenticated_rejection_releases_slot(self):
        self.comments.append(self.comment(9, f"/aljam3 reject {revision(self.issue)}"))
        counts = capacity([self.issue], {1: self.comments}, self.policy)
        self.assertEqual(sum(counts["size"].values()), 0)

    def test_worker_cannot_claim_release_completed(self):
        self.comments.append(self.comment(9, render_record({"type": "released", "revision": revision(self.issue)}), worker=True))
        self.assertEqual(capacity([self.issue], {1: self.comments}, self.policy)["size"]["small"], 1)

    def test_gate_completion_releases_slot(self):
        self.comments.append(self.comment(9, render_record({"type": "released", "revision": revision(self.issue)}), gate=True))
        self.assertEqual(capacity([self.issue], {1: self.comments}, self.policy)["size"]["small"], 0)

    def test_sensitive_path_requires_owner_delivery_command(self):
        self.pull["files"] = [".github/workflows/ci.yml"]
        with self.assertRaisesRegex(ValueError, "Sensitive delivery"):
            delivery(self.issue, self.comments, [self.pull], self.policy)
        bundle = bundle_id(revision(self.issue), [self.pull])
        self.comments.append(self.comment(10, f"/aljam3 delivery {bundle}"))
        delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_independent_task_ids_are_required(self):
        self.comments[-1]["body"] = self.comments[-1]["body"].replace("task-ceo", "task-cto")
        with self.assertRaisesRegex(ValueError, "independent"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_failure_after_qa_pass_blocks_delivery(self):
        self.comments.append({**self.comments[2], "id": 9, "body": self.comments[2]["body"].replace('"pass"', '"fail"')})
        with self.assertRaises(ValueError):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_partial_cross_repo_bundle_is_rejected(self):
        self.issue["body"] = self.issue["body"].replace('"ieasybooks/aljam3-web-app"]', '"ieasybooks/aljam3-web-app","ieasybooks/aljam3-desktop"]')
        self.comments[0]["body"] = f"/aljam3 approve {revision(self.issue)}"
        with self.assertRaisesRegex(ValueError, "Exactly one PR"):
            delivery(self.issue, self.comments, [self.pull], self.policy)

    def test_off_policy_blocks_even_configured_identities(self):
        policy = {**self.policy, "mode": "off"}
        with self.assertRaisesRegex(ValueError, "off"):
            active(policy)

    def test_owner_credentials_cannot_activate_workers(self):
        self.policy["worker"] = self.policy["owner"]
        with self.assertRaisesRegex(ValueError, "separate"):
            active(self.policy)

    def test_pilot_allows_only_one_issue_and_no_production(self):
        self.policy.update(mode="pilot", pilot_issue=1)
        active(self.policy, 1)
        with self.assertRaises(ValueError):
            active(self.policy, 2)
        with self.assertRaisesRegex(ValueError, "Production"):
            active(self.policy, 1, live=True)


if __name__ == "__main__":
    unittest.main()
