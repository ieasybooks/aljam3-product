import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from automation.cli import Product
from automation.policy import render_record, revision

ROOT = Path(__file__).resolve().parents[1]


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.product = Product.__new__(Product)
        self.product.policy = json.loads((ROOT / "policy.json").read_text())
        self.product.policy["gate"] = {"login": "gate[bot]", "app_id": 456}
        self.product.api = Mock()
        self.issue = {"number": 1, "title": "Example", "body": (ROOT / "templates/proposal.md").read_text()}
        self.web = "ieasybooks/aljam3-web-app"
        self.desktop = "ieasybooks/aljam3-desktop"
        self.merged = {"bundle": "bundle", "pulls": [{"repository": self.desktop, "merge": "d" * 40},
                                                     {"repository": self.web, "merge": "a" * 40}]}
        self.product.release_ready = Mock(return_value=(self.issue, [], self.merged))
        self.product.post = Mock()

    def permit(self, repo):
        return {"type": "release-requested", "bundle": "bundle", "repository": repo,
                "sha": "a" * 40, "delivery_id": "unique-permit", "revision": revision(self.issue)}

    def with_permit(self, repo):
        comment = {"id": 1, "user": {"login": "gate[bot]"}, "created_at": "now", "updated_at": "now",
                   "body": render_record(self.permit(repo))}
        self.product.release_ready.return_value = (self.issue, [comment], self.merged)

    def test_server_is_dispatched_before_desktop(self):
        result = self.product.release(1)
        self.assertEqual(result["requested"][0]["repository"], self.web)
        self.assertEqual(self.product.api.request.call_count, 1)
        self.assertIn("kamal-run.yml/dispatches", self.product.api.request.call_args.args[0])

    def test_existing_pending_permit_does_not_redispatch(self):
        self.with_permit(self.web)
        self.product.release_run = Mock(return_value={"status": "in_progress"})
        result = self.product.release(1)
        self.assertIn("waiting_for", result)
        self.product.api.request.assert_not_called()

    def test_lost_dispatch_response_does_not_trigger_duplicate(self):
        self.with_permit(self.web)
        self.product.release_run = Mock(return_value=None)
        self.assertIn("waiting_for", self.product.release(1))
        self.product.api.request.assert_not_called()

    def test_failed_server_blocks_desktop(self):
        self.with_permit(self.web)
        self.product.release_run = Mock(return_value={"status": "completed", "conclusion": "failure"})
        with self.assertRaisesRegex(ValueError, "Previous release failed"):
            self.product.release(1)
        self.product.api.request.assert_not_called()

    def test_successful_server_allows_desktop(self):
        self.with_permit(self.web)
        self.product.release_run = Mock(return_value={"status": "completed", "conclusion": "success"})
        result = self.product.release(1)
        self.assertEqual(result["requested"][0]["repository"], self.desktop)

    def test_release_requires_exact_permit_and_sha(self):
        self.with_permit(self.web)
        with self.assertRaisesRegex(ValueError, "matching release permit"):
            self.product.authorize_release(1, self.web, "a" * 40, "replayed-other-permit")
        with self.assertRaisesRegex(ValueError, "Artifact SHA"):
            self.product.authorize_release(1, self.web, "b" * 40, "unique-permit")
        self.assertTrue(self.product.authorize_release(1, self.web, "a" * 40, "unique-permit")["authorized"])

    def test_untrusted_identity_cannot_write_gate_records(self):
        self.product.api.comment.return_value = {"user": {"login": "worker"}}
        with self.assertRaisesRegex(ValueError, "authorized identity"):
            Product.post(self.product, 1, {"type": "released"})

    def test_ambiguous_run_does_not_count_as_completed(self):
        permit = self.permit(self.web)
        self.product.api.request.return_value = {"workflow_runs": [
            {"display_title": "Aljam3 delivery unique-permit"}, {"display_title": "Aljam3 delivery unique-permit"}]}
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.product.release_run(permit)


if __name__ == "__main__":
    unittest.main()
