from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_review


class WriterReviewTests(unittest.TestCase):
    def test_ship_fix_first_and_rethink_contracts(self) -> None:
        revision = "sha256:" + "a" * 64
        ship = {
            "CANDIDATE_REVISION": revision,
            "VERDICT": "ship",
            "FINDINGS": [{"priority": "P2", "summary": "minor risk", "evidence": ["patch line"]}],
            "EVIDENCE": ["tests pass"],
            "EFFECTS": [],
        }
        self.assertEqual(
            writer_review.validate_review_record(ship, candidate_revision=revision)["VERDICT"],
            "ship",
        )
        fix = dict(ship)
        fix["VERDICT"] = "fix-first"
        fix["FINDINGS"] = [{"priority": "P1", "summary": "blocking", "evidence": ["evidence"]}]
        writer_review.validate_review_record(fix, candidate_revision=revision)
        rethink = dict(ship)
        rethink["VERDICT"] = "rethink"
        writer_review.validate_review_record(rethink, candidate_revision=revision)

    def test_stale_effectful_and_inconsistent_records_fail(self) -> None:
        revision = "sha256:" + "a" * 64
        base = {
            "CANDIDATE_REVISION": revision,
            "VERDICT": "ship",
            "FINDINGS": [],
            "EVIDENCE": [],
            "EFFECTS": [],
        }
        stale = dict(base)
        stale["CANDIDATE_REVISION"] = "other"
        with self.assertRaises(writer_review.WriterReviewError):
            writer_review.validate_review_record(stale, candidate_revision=revision)
        effectful = dict(base)
        effectful["EFFECTS"] = ["write"]
        with self.assertRaises(writer_review.WriterReviewError):
            writer_review.validate_review_record(effectful, candidate_revision=revision)
        invalid = dict(base)
        invalid["FINDINGS"] = [{"priority": "P1", "summary": "bad", "evidence": ["x"]}]
        with self.assertRaisesRegex(writer_review.WriterReviewError, "ship"):
            writer_review.validate_review_record(invalid, candidate_revision=revision)

    def test_prompt_is_bounded_and_marks_evidence_untrusted(self) -> None:
        revision = "sha256:" + "a" * 64
        prompt = writer_review.build_review_prompt(
            candidate_package={"candidate_revision": revision, "value": "untrusted"},
            patch_text="diff --git a/a b/a\n",
        )
        self.assertIn("untrusted evidence", prompt)
        self.assertIn(revision, prompt)
        self.assertIn("EFFECTS must be []", prompt)


if __name__ == "__main__":
    unittest.main()
