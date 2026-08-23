from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skill.runtime.artifacts import (
    ArtifactStore,
    canonical_json_bytes,
    is_artifact_reference,
    substitute_upstream_results,
)
from skill.runtime.limits import ArtifactLimitError, RuntimeLimits
from skill.runtime.schema_contract import (
    build_envelope_schema,
    normalize_provider_result,
    validate_instance,
)
from skill.runtime.state_store import RunStateStore, spec_digest
from skill.runtime.workflow_ir import (
    WorkflowIRValidationError,
    compile_static_ir_to_v2,
    validate_workflow_ir,
)


class SchemaContractTests(unittest.TestCase):
    def test_optional_provider_fields_are_nullable_and_normalized_away(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["name"],
        }
        provider = build_envelope_schema(schema)["properties"]["result"]
        self.assertEqual(provider["required"], ["name", "note"])
        self.assertIn("anyOf", provider["properties"]["note"])
        normalized = normalize_provider_result(
            {"name": "ok", "note": None}, schema
        )
        self.assertEqual(normalized, {"name": "ok"})
        self.assertEqual(validate_instance(normalized, schema), [])

    def test_optional_explicitly_nullable_value_is_preserved(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "note": {"type": ["string", "null"]},
            },
            "required": [],
            "additionalProperties": False,
        }
        normalized = normalize_provider_result({"note": None}, schema)
        self.assertEqual(normalized, {"note": None})
        self.assertEqual(validate_instance(normalized, schema), [])

    def test_required_null_is_not_silently_removed(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        }
        normalized = normalize_provider_result({"name": None}, schema)
        self.assertEqual(normalized, {"name": None})
        self.assertTrue(validate_instance(normalized, schema))


class ArtifactTests(unittest.TestCase):
    def test_large_upstream_value_becomes_content_addressed_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            limits = RuntimeLimits.from_mapping(
                {
                    "max_result_bytes": 4096,
                    "max_log_bytes": 4096,
                    "max_run_artifact_bytes": 65536,
                    "max_upstream_inline_bytes": 16,
                    "max_event_bytes": 4096,
                },
                env={},
            )
            store = ArtifactStore(run_dir, limits)
            value = {"payload": "x" * 200}
            reference = store.put_json("source", value)
            prompt, missing = substitute_upstream_results(
                "use {{result:source}}",
                {"source": {"output": value, "artifact": reference}},
                placeholder_pattern=__import__("re").compile(
                    r"\{\{result:([A-Za-z0-9_-]+)\}\}"
                ),
                store=store,
                max_inline_bytes=16,
            )
            self.assertFalse(missing)
            self.assertIn("UPSTREAM_ARTIFACT_REFERENCE", prompt)
            self.assertIn("sha256:", prompt)
            self.assertTrue(store.resolve_reference(reference).is_file())

    def test_result_limit_is_enforced_before_artifact_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            limits = RuntimeLimits.from_mapping(
                {
                    "max_result_bytes": 32,
                    "max_log_bytes": 4096,
                    "max_run_artifact_bytes": 65536,
                    "max_upstream_inline_bytes": 16,
                    "max_event_bytes": 4096,
                },
                env={},
            )
            store = ArtifactStore(Path(temporary), limits)
            with self.assertRaises(ArtifactLimitError):
                store.put_json("source", {"payload": "x" * 200})

    def test_load_json_revalidates_the_bytes_it_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            limits = RuntimeLimits.from_mapping(
                {
                    "max_result_bytes": 4096,
                    "max_log_bytes": 4096,
                    "max_run_artifact_bytes": 65536,
                    "max_upstream_inline_bytes": 16,
                    "max_event_bytes": 4096,
                },
                env={},
            )
            store = ArtifactStore(Path(temporary), limits)
            reference = store.put_json("source", {"value": "ok"})
            original_resolve = store.resolve_reference

            def replace_after_validation(candidate):
                path = original_resolve(candidate)
                replacement = canonical_json_bytes({"value": "no"})
                self.assertEqual(len(replacement), path.stat().st_size)
                path.write_bytes(replacement)
                return path

            with mock.patch.object(
                store,
                "resolve_reference",
                side_effect=replace_after_validation,
            ):
                with self.assertRaisesRegex(
                    ArtifactLimitError,
                    "digest changed before JSON load",
                ):
                    store.load_json(reference)


class StateStoreTests(unittest.TestCase):
    def test_checkpoint_and_events_are_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            store = RunStateStore(run_dir, max_event_bytes=4096)
            event = store.append_event("run.created", {"name": "fixture"})
            checkpoint = store.write_checkpoint(
                {
                    "spec_digest": "abc",
                    "states": {"a": "pending"},
                    "entries": {},
                    "started": "now",
                    "finished": None,
                }
            )
            self.assertEqual(event["event_version"], 1)
            self.assertEqual(checkpoint["checkpoint_version"], 1)
            self.assertEqual(store.load_checkpoint()["event_sequence"], 1)

    def test_event_journal_cannot_push_run_above_total_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "filler.bin").write_bytes(b"x" * 900)
            store = RunStateStore(
                run_dir,
                max_event_bytes=4096,
                max_run_artifact_bytes=1024,
            )
            with self.assertRaises(ArtifactLimitError):
                store.append_event("large.event", {"payload": "y" * 300})
            self.assertFalse((run_dir / "events.jsonl").exists())

    def test_spec_digest_ignores_mutable_preflight(self) -> None:
        base = {
            "version": 2,
            "name": "fixture",
            "workdir": "/tmp/work",
            "max_concurrency": 1,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
            "tasks": [],
            "preflight": {"codex_version": "one"},
        }
        changed = {**base, "preflight": {"codex_version": "two"}}
        self.assertEqual(spec_digest(base), spec_digest(changed))


class WorkflowIRTests(unittest.TestCase):
    def static_ir(self) -> dict:
        return {
            "version": 3,
            "name": "audit-flow",
            "mode": "workflow",
            "objective": "Audit two independent areas and synthesize evidence.",
            "workdir": "/tmp/work",
            "budgets": {"max_agents": 4, "max_concurrency": 2},
            "nodes": [
                {
                    "id": "inspect",
                    "kind": "agent",
                    "depends_on": [],
                    "config": {"profile": "luna", "prompt": "Inspect."},
                },
                {
                    "id": "judge",
                    "kind": "agent",
                    "depends_on": ["inspect"],
                    "config": {"profile": "sol", "prompt": "Judge."},
                },
            ],
        }

    def test_static_agent_subset_compiles_to_v2(self) -> None:
        normalized = validate_workflow_ir(self.static_ir())
        self.assertTrue(normalized["execution"]["static_v2_compilable"])
        compiled = compile_static_ir_to_v2(normalized)
        self.assertEqual(compiled["version"], 2)
        self.assertEqual(compiled["tasks"][1]["depends_on"], ["inspect"])

    def test_dynamic_nodes_are_versioned_but_not_silently_executed(self) -> None:
        raw = self.static_ir()
        raw["nodes"].append(
            {
                "id": "verify-loop",
                "kind": "loop",
                "depends_on": ["judge"],
                "config": {"max_iterations": 2, "body": ["judge"]},
            }
        )
        raw["budgets"]["max_agents"] = 5
        normalized = validate_workflow_ir(raw)
        self.assertEqual(normalized["execution"]["dynamic_node_kinds"], ["loop"])
        with self.assertRaises(WorkflowIRValidationError):
            compile_static_ir_to_v2(normalized)


if __name__ == "__main__":
    unittest.main()
