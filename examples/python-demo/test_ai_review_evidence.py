import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "ai_review_evidence", Path(__file__).resolve().parent / "tools" / "ai_review_evidence.py"
)
ai_review_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai_review_evidence)


class FakeResponse(io.BytesIO):
    def __init__(self, body, link=None):
        super().__init__(json.dumps(body).encode())
        self.headers = {"Link": link} if link else {}


class FetchReviewsTests(unittest.TestCase):
    def test_follows_next_links_and_sets_a_timeout(self):
        pages = {
            "https://api.test/reviews?page=1": FakeResponse(
                [{"id": 1}], '<https://api.test/reviews?page=2>; rel="next", <https://api.test/reviews?page=2>; rel="last"'
            ),
            "https://api.test/reviews?page=2": FakeResponse([{"id": 2}]),
        }
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append((request.full_url, timeout))
            return pages[request.full_url]

        with mock.patch.object(ai_review_evidence, "urlopen", fake_urlopen):
            reviews = ai_review_evidence.fetch_reviews("https://api.test/reviews?page=1", "token")

        self.assertEqual([review["id"] for review in reviews], [1, 2])
        self.assertEqual([url for url, _ in calls], list(pages))
        self.assertTrue(all(timeout for _, timeout in calls))


if __name__ == "__main__":
    unittest.main()
