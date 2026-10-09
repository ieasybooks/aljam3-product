import unittest
from unittest.mock import Mock

from automation.cli import Product
from automation.github import GitHub


class GitHubTest(unittest.TestCase):
    def test_all_pages_are_counted(self):
        api = GitHub()
        api.request = Mock(side_effect=[list(range(100)), [100]])
        self.assertEqual(len(api.pages("repos/example/product/issues?state=all")), 101)
        self.assertIn("&per_page=100&page=2", api.request.call_args.args[0])

    def test_existing_reservation_blocks_another_owner(self):
        product = Product.__new__(Product)
        product.lock = Mock(return_value={"thread": "existing-thread"})
        with self.assertRaisesRegex(ValueError, "reserved"):
            product.acquire("active", {"thread": "second-thread"})

    def test_cannot_release_someone_elses_reservation(self):
        product = Product.__new__(Product)
        product.lock = Mock(return_value={"sha": "new-claim"})
        product.api = Mock()
        with self.assertRaisesRegex(ValueError, "changed"):
            product.release_lock("active", "old-claim")
        product.api.request.assert_not_called()

    def test_atomic_ref_collision_is_not_treated_as_success(self):
        product = Product.__new__(Product)
        product.path = "repos/example/product"
        product.lock = Mock(return_value=None)
        product.api = Mock()
        product.api.request.side_effect = [{"object": {"sha": "main"}}, {"tree": {"sha": "tree"}},
                                           {"sha": "commit"}, ValueError("ref already exists")]
        with self.assertRaisesRegex(ValueError, "already exists"):
            product.acquire("active", {"thread": "second-thread"})


if __name__ == "__main__":
    unittest.main()
