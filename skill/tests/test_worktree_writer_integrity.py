from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_runtime
from test_worktree_writer_runtime import FakeProcessAdapter, Fixture


class WriterIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        adapter = FakeProcessAdapter(verdict="ship")
        with self.fixture.environment(), self.fixture.preflight():
            self.result = writer_runtime.run_writer(
                package_path=self.fixture.package_path,
                repository=self.fixture.repo,
                expected_package_digest=self.fixture.package.digest,
                expected_head_sha=self.fixture.package.expected_head_sha,
                ack_isolated_worktree_write=True,
                process_adapter=adapter,
            )
        self.run_dir = Path(self.result["candidate"]["candidate_package_path"]).parent

    def tearDown(self) -> None:
        self.fixture.close()

    def test_patch_and_captured_file_tamper_fail_closed(self) -> None:
        patch = self.run_dir / "candidate.patch"
        original = patch.read_bytes()
        patch.write_bytes(original + b"tamper\n")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "patch"):
            writer_runtime.status_writer(self.run_dir)
        patch.write_bytes(original)

        captured = self.run_dir / "candidate-files" / "docs" / "new.md"
        original_file = captured.read_bytes()
        captured.write_bytes(original_file + b"tamper\n")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "candidate file"):
            writer_runtime.status_writer(self.run_dir)

    def test_candidate_checkpoint_outside_path_is_rejected(self) -> None:
        checkpoint_path = self.run_dir / "checkpoint.json"
        summary_path = self.run_dir / "summary.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        outside = Path(tempfile.mkdtemp()) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        checkpoint["candidate"]["candidate_package_path"] = str(outside.resolve())
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["candidate"]["candidate_package_path"] = str(outside.resolve())
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "candidate package path"):
            writer_runtime.status_writer(self.run_dir)

    @unittest.skipIf(os.name == "nt", "symlink creation may require Windows privilege")
    def test_run_evidence_symlink_is_rejected_before_following(self) -> None:
        package = self.run_dir / "candidate-package.json"
        outside = self.run_dir.parent / "outside-candidate.json"
        outside.write_text(package.read_text(encoding="utf-8"), encoding="utf-8")
        package.unlink()
        package.symlink_to(outside)
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "symlink"):
            writer_runtime.status_writer(self.run_dir)

    def test_reviewer_record_lock_event_and_live_candidate_tamper_fail_closed(self) -> None:
        review = self.run_dir / "review-record.json"
        record = json.loads(review.read_text(encoding="utf-8"))
        record["CANDIDATE_REVISION"] = "sha256:" + "0" * 64
        review.write_text(json.dumps(record, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "stale"):
            writer_runtime.status_writer(self.run_dir)
        record["CANDIDATE_REVISION"] = self.result["candidate"]["candidate_revision"]
        review.write_text(json.dumps(record, indent=2), encoding="utf-8")

        lock_path = Path(self.result["lock_path"])
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["run_id"] = "tampered"
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "lock"):
            writer_runtime.status_writer(self.run_dir)
        lock["run_id"] = self.result["run_id"]
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")

        events = self.run_dir / "events.jsonl"
        original_events = events.read_bytes()
        events.write_bytes(original_events + b'{"event_version":1}')
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "journal"):
            writer_runtime.status_writer(self.run_dir)
        events.write_bytes(original_events)

        live = Path(self.result["worktree_path"]) / "docs" / "new.md"
        live.write_text("# Mutated after review\n", encoding="utf-8")
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "candidate changed"):
            writer_runtime.status_writer(self.run_dir)

    def test_cleanup_identity_is_exact(self) -> None:
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "run identity"):
            writer_runtime.cleanup_writer(
                run_dir=self.run_dir,
                expected_run_id="wrong",
                expected_package_digest=self.fixture.package.digest,
                ack_delete_isolated_worktree=True,
            )
        with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "package digest"):
            writer_runtime.cleanup_writer(
                run_dir=self.run_dir,
                expected_run_id=self.result["run_id"],
                expected_package_digest="0" * 64,
                ack_delete_isolated_worktree=True,
            )


if __name__ == "__main__":
    unittest.main()
